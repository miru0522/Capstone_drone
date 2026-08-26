"""
waypoint_mission.py
PX4 Auto 모드 기반 Waypoint 자율비행 모듈.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional

from mavsdk import System
from mavsdk.mission import MissionItem, MissionPlan

logger = logging.getLogger("waypoint_mission")

DEFAULT_ALTITUDE_M = 30.0
DEFAULT_SPEED_MS = 5.0
ACCEPTANCE_RADIUS_M = 3.0
MIN_SAFE_ALTITUDE_M = 20.0  # ★2026-08-21: 서버가 무엇을 주든 이 아래로는 비행 안 함 (안전 하한)

class WaypointMissionController:
    def __init__(self, system: System):
        self.system = system

    def _build_mission_items(self, waypoints, altitude=DEFAULT_ALTITUDE_M, speed=DEFAULT_SPEED_MS):
        items = []
        for wp in waypoints:
            # ★2026-08-21: 서버가 alt_agl(지면기준고도)을 지점별로 지정.
            # 안전 최소고도(20m) 하한을 여기서 강제 적용 - 서버가 20m
            # 미만 값을 주더라도(버그든 의도든) 절대 그 아래로 비행하지 않음.
            requested_alt = wp.get("alt", altitude)
            safe_alt = max(requested_alt, MIN_SAFE_ALTITUDE_M)
            if safe_alt != requested_alt:
                logger.warning(
                    f"고도 {requested_alt}m가 최소 안전고도({MIN_SAFE_ALTITUDE_M}m) 미만 "
                    f"-> {safe_alt}m로 보정"
                )
            item = MissionItem(
                latitude_deg=wp["lat"],
                longitude_deg=wp["lon"],
                relative_altitude_m=safe_alt,
                speed_m_s=speed,
                is_fly_through=True,
                gimbal_pitch_deg=float("nan"),
                gimbal_yaw_deg=float("nan"),
                camera_action=MissionItem.CameraAction.NONE,
                loiter_time_s=float("nan"),
                camera_photo_interval_s=float("nan"),
                acceptance_radius_m=ACCEPTANCE_RADIUS_M,
                yaw_deg=float("nan"),
                camera_photo_distance_m=float("nan"),
                vehicle_action=MissionItem.VehicleAction.NONE,
            )
            items.append(item)
        return items

    async def upload_and_start(self, waypoints, altitude=DEFAULT_ALTITUDE_M, speed=DEFAULT_SPEED_MS):
        if not waypoints:
            logger.warning("빈 waypoint 리스트")
            return False
        try:
            items = self._build_mission_items(waypoints, altitude, speed)
            plan = MissionPlan(items)
            logger.info(f"미션 업로드 중... ({len(items)}개 waypoint)")
            await self.system.mission.upload_mission(plan)
            logger.info("미션 업로드 완료")
            async for is_armed in self.system.telemetry.armed():
                if not is_armed:
                    logger.info("드론 무장 중...")
                    await self.system.action.arm()
                else:
                    logger.info("이미 무장된 상태 - arm 생략")
                break
            # PX4 요구사항: 미션 시작 전 명시적 이륙 필요
            # (STATUSTEXT 확인: "Auto: Missing Takeoff Cmd" 로 실기 검증됨)
            async for in_air in self.system.telemetry.in_air():
                if not in_air:
                    logger.info("이륙 중... (미션 시작 전 필수)")
                    await self.system.action.takeoff()
                    await asyncio.sleep(8.0)  # 이륙고도 도달 대기
                break

            logger.info("미션 시작 (PX4 Auto 모드)")
            await self.system.mission.start_mission()
            return True
        except Exception as e:
            logger.error(f"미션 업로드/시작 실패: {e}")
            return False

    async def pause_mission(self):
        try:
            await self.system.mission.pause_mission()
            logger.info("미션 일시정지")
        except Exception as e:
            logger.error(f"미션 일시정지 실패: {e}")

    async def resume_mission(self):
        try:
            await self.system.mission.start_mission()
            logger.info("미션 재개")
        except Exception as e:
            logger.error(f"미션 재개 실패: {e}")

    async def clear_mission(self):
        try:
            await self.system.mission.clear_mission()
            logger.info("미션 초기화")
        except Exception as e:
            logger.error(f"미션 초기화 실패: {e}")

    async def get_mission_progress(self):
        try:
            progress = await self.system.mission.mission_progress().__anext__()
            return {"current": progress.current, "total": progress.total}
        except Exception as e:
            logger.error(f"진행 상황 조회 실패: {e}")
            return None

    async def wait_for_mission_complete(self, on_complete):
        """
        미션 진행 스트림을 구독해, MAVSDK가 '완주'로 판단하는 시점
        (current >= total, total > 0)에 on_complete() 콜백을 1회 호출.
        완주 후 자동으로 hold()를 걸어 호버링시킨다 (자동착륙 폐지 규정).
        상위(command_receiver.py)에서 asyncio.create_task로 백그라운드
        실행하며, CANCEL_PATROL 등으로 취소될 수 있으므로 CancelledError를
        조용히 흡수한다.
        """
        try:
            async for progress in self.system.mission.mission_progress():
                if progress.total > 0 and progress.current >= progress.total:
                    logger.info("🏁 미션 완주 감지 (mission_progress)")
                    try:
                        await self.system.action.hold()
                    except Exception as e:
                        logger.warning(f"완주 후 hold() 실패: {e}")
                    on_complete()
                    return
        except asyncio.CancelledError:
            logger.debug("완주 감지 태스크 취소됨 (다른 명령으로 상태 전환)")
            raise
        except Exception as e:
            logger.error(f"완주 감지 오류: {e}")

    async def wait_for_arrival(self, target_lat, target_lon, radius_m, on_arrival):
        """
        단일 목적지(스테이션 등)로 향하는 비행에서, 목표 좌표까지의
        거리가 radius_m 이내로 들어오면 on_arrival() 콜백을 1회 호출
        하고 hold()로 호버링시킨다 (RETURN_TO_STATION 도착 감지용).
        mission_progress는 다중 웨이포인트 기준이라 단일 목적지엔
        부적합해, 직접 위치 스트림으로 거리 계산한다.
        """
        import math

        def _haversine_m(lat1, lon1, lat2, lon2):
            R = 6371000.0
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlambda = math.radians(lon2 - lon1)
            a = (math.sin(dphi / 2) ** 2
                 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
            return 2 * R * math.asin(math.sqrt(a))

        try:
            async for position in self.system.telemetry.position():
                dist = _haversine_m(
                    position.latitude_deg, position.longitude_deg,
                    target_lat, target_lon,
                )
                if dist <= radius_m:
                    logger.info(f"🏠 스테이션 도착 감지 (거리 {dist:.1f}m <= {radius_m}m)")
                    try:
                        await self.system.action.hold()
                    except Exception as e:
                        logger.warning(f"도착 후 hold() 실패: {e}")
                    on_arrival()
                    return
        except asyncio.CancelledError:
            logger.debug("도착 감지 태스크 취소됨 (다른 명령으로 상태 전환)")
            raise
        except Exception as e:
            logger.error(f"도착 감지 오류: {e}")


async def _test():
    logging.basicConfig(level=logging.INFO)
    system = System()
    await system.connect(system_address="serial:///dev/pixhawk:115200")
    logger.info("드론 연결 완료")

    controller = WaypointMissionController(system)
    test_waypoints = [
        {"lat": 37.4419, "lon": 127.1430, "alt": 30},
        {"lat": 37.4422, "lon": 127.1435, "alt": 30},
        {"lat": 37.4425, "lon": 127.1432, "alt": 30},
    ]
    items = controller._build_mission_items(test_waypoints)
    plan = MissionPlan(items)
    await system.mission.upload_mission(plan)
    logger.info(f"✅ 테스트 미션 업로드 성공 ({len(test_waypoints)}개 waypoint)")


if __name__ == "__main__":
    asyncio.run(_test())
