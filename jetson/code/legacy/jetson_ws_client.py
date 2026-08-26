"""
jetson_ws_client.py
Jetson 드론 클라이언트. FastAPI WebSocket 서버와 연결하여 드론 정보를 송수신.

역할:
- FastAPI 서버의 /ws/drone 에 연결
- MAVSDK로 드론 상태 주기적 수집 (위치, 배터리, 상태 등)
- 상태를 서버로 전송 (telemetry)
- 서버에서 받은 명령 처리 (arm/disarm/takeoff/land/waypoint)
"""

import asyncio
import json
import logging
import time
from typing import Optional, Dict, Any

import websockets
from mavsdk import System
from mavsdk.action import ActionError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ws_client")

# ─── 설정값 ──────────────────────────────────────────────────
FASTAPI_WS_URL = "ws://localhost:8000/ws/drone"  # FastAPI 서버 주소
MAVSDK_CONNECTION_URI = "serial:///dev/ttyACM0:115200"  # 드론 연결 (USB Pixhawk)
TELEMETRY_INTERVAL_SEC = 1.0  # 1초마다 상태 전송
RECONNECT_INTERVAL_SEC = 5.0  # 연결 재시도 간격


class DroneClient:
    def __init__(self):
        self.system: Optional[System] = None
        self.ws = None
        self.running = False
        self.last_telemetry_time = 0.0

    async def connect_drone(self) -> bool:
        """MAVSDK로 드론 연결"""
        try:
            self.system = System()
            await self.system.connect(system_address=MAVSDK_CONNECTION_URI)
            logger.info("드론 연결 성공")
            return True
        except Exception as e:
            logger.error(f"드론 연결 실패: {e}")
            return False

    async def disconnect_drone(self):
        """드론 연결 해제"""
        if self.system:
            logger.info("드론 연결 해제")

    async def get_drone_state(self) -> Dict[str, Any]:
        """현재 드론 상태 수집"""
        if not self.system:
            return {}

        try:
            position = await self.system.telemetry.position().__anext__()
            battery = await self.system.telemetry.battery().__anext__()
            attitude = await self.system.telemetry.attitude_euler_degrees().__anext__()
            gps_info = await self.system.telemetry.gps_info().__anext__()
            armed = await self.system.telemetry.armed().__anext__()
            in_air = await self.system.telemetry.in_air().__anext__()

            return {
                "lat": position.latitude_deg,
                "lon": position.longitude_deg,
                "alt": position.absolute_altitude_m,
                "heading": attitude.yaw_deg,
                "roll": attitude.roll_deg,
                "pitch": attitude.pitch_deg,
                "battery": int(battery.remaining_percent * 100),
                "gps_sats": gps_info.num_satellites,
                "is_armed": armed,
                "is_in_air": in_air,
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.error(f"텔레메트리 수집 실패: {e}")
            return {}

    async def handle_command(self, cmd_data: Dict[str, Any]) -> bool:
        """서버에서 받은 명령 처리"""
        if not self.system:
            return False

        cmd = cmd_data.get("cmd")
        params = cmd_data.get("params", {})

        try:
            if cmd == "arm":
                await self.system.action.arm()
                logger.info("드론 무장")
                return True
            elif cmd == "disarm":
                await self.system.action.disarm()
                logger.info("드론 해제")
                return True
            elif cmd == "takeoff":
                await self.system.action.takeoff()
                logger.info("이륙")
                return True
            elif cmd == "land":
                await self.system.action.land()
                logger.info("착륙")
                return True
            elif cmd == "goto_waypoint":
                lat = params.get("lat", 0.0)
                lon = params.get("lon", 0.0)
                alt = params.get("alt", 50)
                logger.info(f"Waypoint로 이동: ({lat:.4f}, {lon:.4f}, {alt}m)")
                return True
            else:
                logger.warning(f"알 수 없는 명령: {cmd}")
                return False
        except ActionError as e:
            logger.error(f"명령 실행 오류: {e}")
            return False

    async def run(self):
        """메인 루프: 드론 연결 → 상태 수집 → WebSocket으로 전송"""
        self.running = True

        while not await self.connect_drone():
            await asyncio.sleep(RECONNECT_INTERVAL_SEC)

        while self.running:
            try:
                async with websockets.connect(FASTAPI_WS_URL) as ws:
                    self.ws = ws
                    logger.info(f"FastAPI 서버 연결: {FASTAPI_WS_URL}")

                    await asyncio.gather(
                        self._send_telemetry_loop(),
                        self._receive_commands_loop(),
                    )

            except websockets.exceptions.WebSocketException as e:
                logger.error(f"WebSocket 연결 오류: {e}")
                await asyncio.sleep(RECONNECT_INTERVAL_SEC)
            except Exception as e:
                logger.exception(f"오류: {e}")
                await asyncio.sleep(RECONNECT_INTERVAL_SEC)

        await self.disconnect_drone()

    async def _send_telemetry_loop(self):
        """주기적으로 드론 상태를 서버로 전송"""
        while self.running:
            try:
                now = time.time()
                if now - self.last_telemetry_time >= TELEMETRY_INTERVAL_SEC:
                    state = await self.get_drone_state()
                    if state:
                        msg = json.dumps({"type": "telemetry", "data": state})
                        await self.ws.send(msg)
                        self.last_telemetry_time = now
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"텔레메트리 송신 오류: {e}")
                break

    async def _receive_commands_loop(self):
        """서버에서 명령 수신 및 처리"""
        while self.running:
            try:
                msg_str = await self.ws.recv()
                msg = json.loads(msg_str)

                if msg.get("type") == "command":
                    success = await self.handle_command(msg)
                    if success:
                        logger.info(f"명령 처리 완료: {msg.get('cmd')}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"명령 수신 오류: {e}")
                break

    def stop(self):
        """클라이언트 종료"""
        self.running = False


async def main():
    client = DroneClient()
    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("종료 신호 수신")
        client.stop()


if __name__ == "__main__":
    asyncio.run(main())
