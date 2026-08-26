"""
test_web_client2.py
start_mission (다중 waypoint) 명령으로 INVALID_ARGUMENT 원인 재현/검증
"""

import asyncio
import json
import websockets

FASTAPI_WS_CLIENT_URL = "ws://localhost:8000/ws/client"


async def test_client():
    async with websockets.connect(FASTAPI_WS_CLIENT_URL) as ws:
        print("✅ /ws/client 연결 성공")

        initial = await ws.recv()
        print(f"📡 초기 상태: {initial}")

        # 2개 이상 waypoint로 테스트
        test_cmd = {
            "type": "command",
            "cmd": "start_mission",
            "params": {
                "waypoints": [
                    {"lat": 37.4419, "lon": 127.1430, "alt": 30},
                    {"lat": 37.4422, "lon": 127.1435, "alt": 30},
                ],
                "altitude": 30,
                "speed": 5,
            }
        }
        await ws.send(json.dumps(test_cmd))
        print(f"📤 명령 전송: {test_cmd}")

        try:
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"📥 서버 응답: {response}")
        except asyncio.TimeoutError:
            print("⏱️ 응답 타임아웃")


if __name__ == "__main__":
    asyncio.run(test_client())
