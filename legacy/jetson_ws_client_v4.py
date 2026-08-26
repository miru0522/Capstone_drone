"""
jetson_ws_client_v4.py
waypoint_mission.py 연동 버전 - goto_waypoint 명령 실제 구현 포함
"""

import asyncio
import json
import logging
import time
from typing import Optional, Dict, Any, List

import websockets
from mavsdk import System

from waypoint_mission import WaypointMissionController

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ws_client")

FASTAPI_WS_URL = "ws://localhost:8000/ws/drone"
MAVSDK_CONNECTION_URI = "serial:///dev/ttyACM0:115200"
TELEMETRY_INTERVAL_SEC = 1.0


class DroneClient:
    def __init__(self):
        self.system: Optional[System] = None
        self.mission_controller: Optional[WaypointMissionController] = None
        self.ws = None
        self.running = False
        self._pending_waypoints: List[Dict[str, float]] = []

    async def connect_drone(self) -> bool:
        try:
            self.system = System()
            logger.info(f"드론 연결 시도: {MAVSDK_CONNECTION_URI}")
            await asyncio.wait_for(
                self.system.connect(system_address=MAVSDK_CONNECTION_URI),
                timeout=10.0
            )
            await asyncio.sleep(2.0)
            self.mission_controller = WaypointMissionController(self.system)
            logger.info("✅ 드론 연결 성공")
            return True
        except Exception as e:
            logger.error(f"❌ 드론 연결 실패: {e}")
            return False

    async def get_drone_telemetry(self) -> Dict[str, Any]:
        if not self.system:
            return {}
        state = {"timestamp": time.time()}
        try:
            try:
                pos = await asyncio.wait_for(self.system.telemetry.position().__anext__(), timeout=1.0)
                state["lat"] = pos.latitude_deg
                state["lon"] = pos.longitude_deg
                state["alt"] = pos.absolute_altitude_m
            except Exception:
                pass
            try:
                batt = await asyncio.wait_for(self.system.telemetry.battery().__anext__(), timeout=1.0)
                state["battery"] = int(batt.remaining_percent * 100)
            except Exception:
                pass
            try:
                armed = await asyncio.wait_for(self.system.telemetry.armed().__anext__(), timeout=1.0)
                state["is_armed"] = armed
            except Exception:
                pass
            try:
                in_air = await asyncio.wait_for(self.system.telemetry.in_air().__anext__(), timeout=1.0)
                state["is_in_air"] = in_air
            except Exception:
                pass

            # 미션 진행 상황도 포함 (waypoint 비행 중일 때)
            if self.mission_controller:
                progress = await self.mission_controller.get_mission_progress()
                if progress:
                    state["mission_current"] = progress["current"]
                    state["mission_total"] = progress["total"]

            if len(state) > 1:
                logger.info(f"📡 텔레메트리: {state}")
                return state
            return {}
        except Exception as e:
            logger.error(f"⚠️ 텔레메트리 오류: {e}")
            return {}

    async def handle_command(self, cmd_data: Dict[str, Any]) -> bool:
        if not self.system:
            return False

        cmd = cmd_data.get("cmd")
        params = cmd_data.get("params", {})

        try:
            if cmd == "arm":
                await self.system.action.arm()
                logger.info("🔧 드론 무장")
                return True
            elif cmd == "disarm":
                await self.system.action.disarm()
                logger.info("🔧 드론 해제")
                return True
            elif cmd == "takeoff":
                await self.system.action.takeoff()
                logger.info("🚀 이륙")
                return True
            elif cmd == "land":
                await self.system.action.land()
                logger.info("🛬 착륙")
                return True
            elif cmd == "goto_waypoint":
                # 단일 waypoint -> 리스트로 감싸서 미션 1개로 처리
                lat = params.get("lat")
                lon = params.get("lon")
                alt = params.get("alt", 30.0)
                if lat is None or lon is None:
                    logger.warning("goto_waypoint: lat/lon 누락")
                    return False
                success = await self.mission_controller.upload_and_start(
                    waypoints=[{"lat": lat, "lon": lon, "alt": alt}],
                    altitude=alt,
                )
                logger.info(f"🎯 단일 Waypoint 미션 {'시작됨' if success else '실패'}: ({lat:.5f}, {lon:.5f})")
                return success
            elif cmd == "start_mission":
                # 여러 waypoint (지도에서 다중 클릭) -> 순찰 경로
                waypoints = params.get("waypoints", [])
                altitude = params.get("altitude", 30.0)
                speed = params.get("speed", 5.0)
                success = await self.mission_controller.upload_and_start(
                    waypoints=waypoints, altitude=altitude, speed=speed
                )
                logger.info(f"🗺️ 순찰 미션 {'시작됨' if success else '실패'} ({len(waypoints)}개 지점)")
                return success
            elif cmd == "pause_mission":
                await self.mission_controller.pause_mission()
                return True
            elif cmd == "resume_mission":
                await self.mission_controller.resume_mission()
                return True
            elif cmd == "clear_mission":
                await self.mission_controller.clear_mission()
                return True
            else:
                logger.warning(f"❓ 미지원 명령: {cmd}")
                return False
        except Exception as e:
            logger.error(f"❌ 명령 오류: {e}")
            return False

    async def run(self):
        self.running = True
        while not await self.connect_drone():
            logger.info("⏳ 5초 후 재시도...")
            await asyncio.sleep(5.0)

        while self.running:
            try:
                async with websockets.connect(FASTAPI_WS_URL) as ws:
                    self.ws = ws
                    logger.info("✅ FastAPI 서버 연결")
                    await asyncio.gather(
                        self._send_telemetry_loop(),
                        self._receive_commands_loop(),
                    )
            except Exception as e:
                logger.error(f"❌ WebSocket 오류: {e}")
                await asyncio.sleep(5.0)

    async def _send_telemetry_loop(self):
        while self.running:
            try:
                state = await self.get_drone_telemetry()
                if state and self.ws:
                    await self.ws.send(json.dumps({"type": "telemetry", "data": state}))
                await asyncio.sleep(TELEMETRY_INTERVAL_SEC)
            except Exception as e:
                logger.error(f"송신 오류: {e}")
                break

    async def _receive_commands_loop(self):
        while self.running:
            try:
                if self.ws:
                    msg_str = await self.ws.recv()
                    msg = json.loads(msg_str)
                    if msg.get("type") == "command":
                        await self.handle_command(msg)
            except Exception as e:
                logger.error(f"수신 오류: {e}")
                break

    def stop(self):
        self.running = False


async def main():
    client = DroneClient()
    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("🛑 종료")
        client.stop()


if __name__ == "__main__":
    asyncio.run(main())
