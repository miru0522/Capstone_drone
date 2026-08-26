"""
jetson_ws_client_v3.py
버퍼 리셋 추가 - MAVSDK 3.0.1 호환
"""

import asyncio
import json
import logging
import time
from typing import Optional, Dict, Any

import websockets
from mavsdk import System

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ws_client")

FASTAPI_WS_URL = "ws://localhost:8000/ws/drone"
MAVSDK_CONNECTION_URI = "serial:///dev/ttyACM0:115200"
TELEMETRY_INTERVAL_SEC = 1.0


class DroneClient:
    def __init__(self):
        self.system: Optional[System] = None
        self.ws = None
        self.running = False

    async def connect_drone(self) -> bool:
        """MAVSDK 드론 연결"""
        try:
            self.system = System()
            logger.info(f"드론 연결 시도: {MAVSDK_CONNECTION_URI}")
            
            # 연결 시도
            await asyncio.wait_for(
                self.system.connect(system_address=MAVSDK_CONNECTION_URI),
                timeout=10.0
            )
            
            # 연결 후 안정화 대기
            await asyncio.sleep(2.0)
            logger.info("✅ 드론 연결 성공")
            return True
        except asyncio.TimeoutError:
            logger.error("❌ 드론 연결 타임아웃")
            return False
        except Exception as e:
            logger.error(f"❌ 드론 연결 실패: {e}")
            return False

    async def get_drone_telemetry(self) -> Dict[str, Any]:
        """
        드론 상태 수집 - 더 유연한 에러 처리
        개별 텔레메트리가 실패해도 계속 진행
        """
        if not self.system:
            return {}

        state = {"timestamp": time.time()}

        try:
            # 위치
            try:
                pos = await asyncio.wait_for(
                    self.system.telemetry.position().__anext__(),
                    timeout=1.0
                )
                state["lat"] = pos.latitude_deg
                state["lon"] = pos.longitude_deg
                state["alt"] = pos.absolute_altitude_m
            except:
                pass

            # 배터리
            try:
                batt = await asyncio.wait_for(
                    self.system.telemetry.battery().__anext__(),
                    timeout=1.0
                )
                state["battery"] = int(batt.remaining_percent * 100)
            except:
                pass

            # 자세
            try:
                att = await asyncio.wait_for(
                    self.system.telemetry.attitude_euler_degrees().__anext__(),
                    timeout=1.0
                )
                state["heading"] = att.yaw_deg
            except:
                pass

            # GPS
            try:
                gps = await asyncio.wait_for(
                    self.system.telemetry.gps_info().__anext__(),
                    timeout=1.0
                )
                state["gps_sats"] = gps.num_satellites
            except:
                pass

            # 상태
            try:
                armed = await asyncio.wait_for(
                    self.system.telemetry.armed().__anext__(),
                    timeout=1.0
                )
                state["is_armed"] = armed
            except:
                pass

            try:
                in_air = await asyncio.wait_for(
                    self.system.telemetry.in_air().__anext__(),
                    timeout=1.0
                )
                state["is_in_air"] = in_air
            except:
                pass

            if len(state) > 1:  # timestamp 제외하고 하나라도 있으면
                logger.info(f"📡 텔레메트리: {state}")
                return state
            else:
                return {}

        except Exception as e:
            logger.error(f"⚠️ 텔레메트리 오류: {e}")
            return {}

    async def handle_command(self, cmd_data: Dict[str, Any]) -> bool:
        """서버에서 받은 명령 처리"""
        if not self.system:
            return False

        cmd = cmd_data.get("cmd")
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
            else:
                logger.warning(f"❓ 미지원 명령: {cmd}")
                return False
        except Exception as e:
            logger.error(f"❌ 명령 오류: {e}")
            return False

    async def run(self):
        """메인 루프"""
        self.running = True

        while not await self.connect_drone():
            logger.info("⏳ 5초 후 재시도...")
            await asyncio.sleep(5.0)

        while self.running:
            try:
                async with websockets.connect(FASTAPI_WS_URL) as ws:
                    self.ws = ws
                    logger.info(f"✅ FastAPI 서버 연결")

                    await asyncio.gather(
                        self._send_telemetry_loop(),
                        self._receive_commands_loop(),
                    )

            except Exception as e:
                logger.error(f"❌ WebSocket 오류: {e}")
                await asyncio.sleep(5.0)

    async def _send_telemetry_loop(self):
        """주기적 텔레메트리 전송"""
        while self.running:
            try:
                state = await self.get_drone_telemetry()
                if state and self.ws:
                    msg = json.dumps({"type": "telemetry", "data": state})
                    await self.ws.send(msg)
                await asyncio.sleep(TELEMETRY_INTERVAL_SEC)
            except Exception as e:
                logger.error(f"송신 오류: {e}")
                break

    async def _receive_commands_loop(self):
        """명령 수신"""
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
