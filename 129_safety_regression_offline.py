#!/usr/bin/env python3
"""실장치 부작용 없이 P0 안전 변경을 검증하는 회귀 테스트."""

import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest


class _MissionItem:
    class CameraAction:
        NONE = 0

    class VehicleAction:
        NONE = 0

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _MissionPlan:
    def __init__(self, items):
        self.items = items


def _install_import_stubs():
    mavsdk = types.ModuleType("mavsdk")
    mavsdk.System = object
    mission = types.ModuleType("mavsdk.mission")
    mission.MissionItem = _MissionItem
    mission.MissionPlan = _MissionPlan
    sys.modules["mavsdk"] = mavsdk
    sys.modules["mavsdk.mission"] = mission

    stomp = types.ModuleType("stomp")
    stomp.ConnectionListener = object
    stomp.WSStompConnection = object
    sys.modules["stomp"] = stomp

    websocket = types.ModuleType("websocket")
    websocket.create_connection = lambda *args, **kwargs: None
    sys.modules["websocket"] = websocket

    requests = types.ModuleType("requests")
    requests.post = lambda *args, **kwargs: None
    sys.modules["requests"] = requests


_install_import_stubs()

_TEMP_PATH = Path(__file__).with_name(".safety_test_state")
_TEMP_PATH.mkdir(exist_ok=True)
os.environ["STATUS_STATE_PATH"] = str(_TEMP_PATH / "status.json")
os.environ["STREAM_REQUEST_STATE_PATH"] = str(_TEMP_PATH / "stream.json")
os.environ["ANOMALY_HOLD_STATE_PATH"] = str(_TEMP_PATH / "anomaly.json")

from battery_utils import BatteryPercentNormalizer
from state_store import atomic_write_json, read_json

waypoint_mission = importlib.import_module("waypoint_mission")
command_receiver = importlib.import_module("command_receiver")


class BatteryTests(unittest.TestCase):
    def test_observed_percent_contract(self):
        normalizer = BatteryPercentNormalizer("auto")
        self.assertEqual(normalizer.normalize(96.0), 96.0)
        self.assertEqual(normalizer.unit, "percent")

    def test_fraction_contract(self):
        normalizer = BatteryPercentNormalizer("fraction")
        self.assertAlmostEqual(normalizer.normalize(0.407), 40.7)

    def test_non_finite_and_range_rejected(self):
        normalizer = BatteryPercentNormalizer("percent")
        for value in (float("nan"), float("inf"), -1.0, 101.0):
            with self.assertRaises(ValueError):
                normalizer.normalize(value)


class AtomicStateTests(unittest.TestCase):
    def test_concurrent_read_never_observes_partial_json(self):
        path = str(_TEMP_PATH / "atomic.json")
        errors = []

        def writer():
            for index in range(200):
                atomic_write_json(path, {"index": index, "payload": "x" * 4096})

        thread = threading.Thread(target=writer)
        thread.start()
        while thread.is_alive():
            value = read_json(path, None)
            if value is not None and not isinstance(value.get("index"), int):
                errors.append(value)
        thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(read_json(path, {})["index"], 199)


class WaypointTests(unittest.IsolatedAsyncioTestCase):
    def test_agl_to_home_relative_altitude(self):
        controller = waypoint_mission.WaypointMissionController(object())
        items = controller._build_mission_items(
            [{
                "lat": 37.0,
                "lon": 127.0,
                "alt_agl": 30.0,
                "ground_elevation_m": 125.0,
            }],
            home_absolute_altitude_m=100.0,
        )
        self.assertEqual(items[0].relative_altitude_m, 55.0)

    def test_ground_elevation_requires_home_altitude(self):
        controller = waypoint_mission.WaypointMissionController(object())
        with self.assertRaises(ValueError):
            controller._build_mission_items([{
                "lat": 37.0,
                "lon": 127.0,
                "alt_agl": 30.0,
                "ground_elevation_m": 125.0,
            }])


class _Action:
    def __init__(self):
        self.calls = []
        self.kill_error = None
        self.land_error = None

    async def arm(self):
        self.calls.append("arm")

    async def takeoff(self):
        self.calls.append("takeoff")

    async def hold(self):
        self.calls.append("hold")

    async def land(self):
        self.calls.append("land")
        if self.land_error:
            raise self.land_error

    async def kill(self):
        self.calls.append("kill")
        if self.kill_error:
            raise self.kill_error


class _Telemetry:
    async def armed(self):
        yield False

    async def in_air(self):
        yield False


class _System:
    def __init__(self):
        self.action = _Action()
        self.telemetry = _Telemetry()


class _Mission:
    def __init__(self):
        self.upload_calls = 0
        self.uploaded_waypoints = None
        self.current_mission_kind = None
        self.last_progress_current = 0
        self.resume_calls = 0

    async def upload_and_start(self, *args, **kwargs):
        self.upload_calls += 1
        self.uploaded_waypoints = args[0]
        self.current_mission_kind = kwargs.get("mission_kind")
        return True

    async def resume_mission(self):
        self.resume_calls += 1
        return True

    async def wait_for_mission_complete(self, callback):
        return None


class CommandSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.handler = command_receiver.DroneCommandHandler(asyncio.get_running_loop())
        self.handler.system = _System()
        self.handler.mission = _Mission()

    async def test_start_without_route_never_arms_or_takes_off(self):
        await self.handler._start_patrol(0)
        self.assertEqual(self.handler.system.action.calls, [])
        self.assertEqual(self.handler.mission.upload_calls, 0)
        self.assertEqual(self.handler._status, "IDLE")

    async def test_restart_recovery_uses_actual_ground_state(self):
        await self.handler.recover_initial_state()
        state = read_json(command_receiver.STATUS_STATE_PATH)
        self.assertEqual(state["status"], "IDLE")
        self.assertIsNone(state["currentAction"])

    async def test_anomaly_hold_reports_success_and_paused(self):
        request_id = "hold-success"
        atomic_write_json(command_receiver.ANOMALY_HOLD_STATE_PATH, {
            "request_id": request_id,
            "requested_at": 1.0,
            "status": "processing",
        })
        self.handler._status = "PATROLLING"
        await self.handler._anomaly_hold(0, request_id)
        self.assertEqual(self.handler._status, "PAUSED")
        self.assertEqual(read_json(command_receiver.ANOMALY_HOLD_STATE_PATH)["status"], "succeeded")

    async def test_land_failure_restores_previous_status(self):
        self.handler._status = "PATROLLING"
        self.handler.system.action.land_error = RuntimeError("land rejected")
        await self.handler._land(0)
        self.assertEqual(self.handler._status, "PATROLLING")
        state = read_json(command_receiver.STATUS_STATE_PATH)
        self.assertEqual(state["currentAction"], "LAND_FAILED")

    async def test_unconfirmed_kill_is_not_reported_idle(self):
        self.handler._status = "PATROLLING"
        self.handler.system.action.kill_error = asyncio.TimeoutError()
        await self.handler._emergency_stop(0)
        self.assertEqual(self.handler._status, "PATROLLING")
        state = read_json(command_receiver.STATUS_STATE_PATH)
        self.assertEqual(state["currentAction"], "EMERGENCY_STOP_UNCONFIRMED")

    async def test_resume_uses_loaded_patrol_mission(self):
        self.handler._route = [{"lat": 37.0, "lon": 127.0, "alt_agl": 30.0}]
        self.handler._route_version = 2
        self.handler._loaded_patrol_route_version = 2
        self.handler._status = "PAUSED"
        self.handler.mission.current_mission_kind = "patrol"
        await self.handler._resume_patrol(0)
        self.assertEqual(self.handler.mission.resume_calls, 1)
        self.assertEqual(self.handler.mission.upload_calls, 0)
        self.assertEqual(self.handler._status, "PATROLLING")

    async def test_resume_after_return_uploads_remaining_route(self):
        self.handler._route = [
            {"lat": 37.0 + i / 1000, "lon": 127.0, "alt_agl": 30.0}
            for i in range(5)
        ]
        self.handler._route_version = 3
        self.handler._loaded_patrol_route_version = 3
        self.handler._patrol_resume_index = 2
        self.handler._status = "RETURNING"
        self.handler.mission.current_mission_kind = "return"
        await self.handler._resume_patrol(0)
        self.assertEqual(self.handler.mission.resume_calls, 0)
        self.assertEqual(self.handler.mission.uploaded_waypoints, self.handler._route[2:])
        self.assertEqual(self.handler._patrol_mission_base_index, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
