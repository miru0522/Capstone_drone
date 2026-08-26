"""
jetson_ws_client_v2.py
수정된 버전 - 타임아웃 및 예외 처리 추가
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
TELEMETRY_INTERVAL_SEC = 2.0
RECONNECT_INTERVAL_SEC = 5.0


class DroneClient:
    def __init__(self):
        self.system: Optional[System] = None
        self.ws = None
        self.running = False

    async def connect_drone(self) -> bool:
        """MAVSDK로 드론 연결"""
        try:
            self.system = System()
            logger.info(f"드론 연결 시도: {MAVSDK_CONNECTION_URI}")
            await asyncio.wait_for(
                self.system.connect(system_address=MAVSDK_CONNECTION_URI),
                timeout=10.0
            )
            logger.info("✅ 드론 연결 성공")
            return True
        except asyncio.TimeoutError:
            logger.error("❌ 드론 연결 타임아웃 (10초)")
            return False
        except Exception as e:
            logger.error(f"❌ 드론 연결 실패: {e}")
            return False

    async def get_drone_state(self) -> Dict[str, Any]:
        """드론 상태 수집 (타임아웃 추가)"""
        if not self.system:
            return {}

        try:
            # 각 텔레메트리마다 타임아웃 설정 (2초)
            position = await asyncio.wait_for(
                self.system.telemetry.position().__anext__(),
                timeout=2.0
            )
            battery = await asyncio.wait_for(
                self.system.telemetry.battery().__anext__(),
                timeout=2.0
            )
            attitude = await asyncio.wait_for(
                self.system.telemetry.attitude_euler_degrees().__anext__(),
                timeout=2.0
            )
            gps_info = await asyncio.wait_for(
                self.system.telemetry.gps_info().__anext__(),
                timeout=2.0
            )
            armed = await asyncio.wait_for(
                self.system.telemetry.armed().__anext__(),
                timeout=2.0
            )
            in_air = await asyncio.wait_for(
                self.system.telemetry.in_air().__anext__(),
                timeout=2.0
            )

            state = {
                "lat": position.latitude_deg,
                "lon": position.longitude_deg,
                "alt": position.absolute_altitude_m,
                "heading": attitude.yaw_deg,
                "battery": int(battery.remaining_percent * 100),
                "gps_sats": gps_info.num_satellites,
                "is_armed": armed,
                "is_in_air": in_air,
                "timestamp": time.time(),
            }
            logger.info(f"📡 텔레메트리 수신: lat={state['lat']:.4f}, lon={state['lon']:.4f}, alt={state['alt']:.1f}m, battery={state['battery']}%")
            return state

        except asyncio.TimeoutError:
            logger.warning("⏱️ 텔레메트리 타임아웃")
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
            logger.info(f"⏳ {RECONNECT_INTERVAL_SEC}초 후 재시도...")
            await asyncio.sleep(RECONNECT_INTERVAL_SEC)

        while self.running:
            try:
                async with websockets.connect(FASTAPI_WS_URL) as ws:
                    self.ws = ws
                    logger.info(f"✅ FastAPI 서버 연결: {FASTAPI_WS_URL}")

                    await asyncio.gather(
                        self._send_telemetry_loop(),
                        self._receive_commands_loop(),
                    )

            except Exception as e:
                logger.error(f"❌ WebSocket 오류: {e}")
                await asyncio.sleep(RECONNECT_INTERVAL_SEC)

    async def _send_telemetry_loop(self):
        """주기적으로 드론 상태 전송"""
        while self.running:
            try:
                state = await self.get_drone_state()
                if state:
                    msg = json.dumps({"type": "telemetry", "data": state})
                    await self.ws.send(msg)
                await asyncio.sleep(TELEMETRY_INTERVAL_SEC)
            except Exception as e:
                logger.error(f"텔레메트리 송신 오류: {e}")
                break

    async def _receive_commands_loop(self):
        """서버에서 명령 수신"""
        while self.running:
            try:
                msg_str = await self.ws.recv()
                msg = json.loads(msg_str)
                if msg.get("type") == "command":
                    await self.handle_command(msg)
            except Exception as e:
                logger.error(f"명령 수신 오류: {e}")
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
