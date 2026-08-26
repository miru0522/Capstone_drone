"""
test_web_client.py
웹 클라이언트 시뮬레이터 - /ws/client 에 접속해서
1) 드론 텔레메트리 수신 확인
2) goto_waypoint 명령 전송 테스트 (GPS 없어도 명령 전달 자체는 확인 가능)
"""

import asyncio
import json
import websockets

FASTAPI_WS_CLIENT_URL = "ws://localhost:8000/ws/client"


async def test_client():
    async with websockets.connect(FASTAPI_WS_CLIENT_URL) as ws:
        print("✅ /ws/client 연결 성공")

        # 연결 직후 서버가 보내는 초기 telemetry 수신
        initial = await ws.recv()
        print(f"📡 초기 상태: {initial}")

        # 테스트 명령 전송 (GPS 없어도 명령 전달 경로는 검증 가능)
        test_cmd = {
            "type": "command",
            "cmd": "goto_waypoint",
            "params": {"lat": 37.4419, "lon": 127.1430, "alt": 30}
        }
        await ws.send(json.dumps(test_cmd))
        print(f"📤 명령 전송: {test_cmd}")

        # 서버 응답 대기 (5초)
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"📥 서버 응답: {response}")
        except asyncio.TimeoutError:
            print("⏱️ 응답 타임아웃 (5초)")

        # 추가로 몇 초간 telemetry 브로드캐스트도 수신해보기
        print("\n--- 5초간 추가 telemetry 수신 대기 ---")
        try:
            for _ in range(3):
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                print(f"📡 {msg}")
        except asyncio.TimeoutError:
            print("(추가 메시지 없음)")


if __name__ == "__main__":
    asyncio.run(test_client())
