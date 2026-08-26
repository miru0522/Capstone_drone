"""
fastapi_ws_server.py
WebSocket 기반 드론 정보 중계 서버.

역할:
- /ws/drone: Jetson 클라이언트 연결 (드론 상태 수신)
- /ws/client: 웹 클라이언트 연결 (상태 조회 + 명령 전송)
- 메시지 브로드캐스팅: 드론 상태 → 모든 웹 클라이언트
"""

import json
import asyncio
import logging
from datetime import datetime
from typing import Set, Optional, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ws_server")

app = FastAPI(title="Drone WebSocket Server")

# ─── 상태 저장소 ─────────────────────────────────────────────
drone_state: Dict[str, Any] = {
    "lat": 0.0,
    "lon": 0.0,
    "alt": 0.0,
    "heading": 0,
    "battery": 0,
    "is_armed": False,
    "is_in_air": False,
    "gps_sats": 0,
    "timestamp": None,
    "connected": False,
}

# ─── 클라이언트 관리 ─────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_clients: Set[WebSocket] = set()
        self.drone_connection: Optional[WebSocket] = None

    async def connect_client(self, websocket: WebSocket):
        await websocket.accept()
        self.active_clients.add(websocket)
        logger.info(f"웹 클라이언트 연결 (총 {len(self.active_clients)}명)")

    async def connect_drone(self, websocket: WebSocket):
        await websocket.accept()
        self.drone_connection = websocket
        drone_state["connected"] = True
        logger.info("드론(Jetson) 연결됨")
        await self.broadcast_status("드론 연결됨")

    async def disconnect_client(self, websocket: WebSocket):
        self.active_clients.discard(websocket)
        logger.info(f"웹 클라이언트 연결 해제 (남은 클라이언트: {len(self.active_clients)}명)")

    async def disconnect_drone(self):
        self.drone_connection = None
        drone_state["connected"] = False
        logger.info("드론 연결 끊김")
        await self.broadcast_status("드론 연결 끊김")

    async def broadcast_telemetry(self, data: Dict[str, Any]):
        """드론 상태를 모든 웹 클라이언트에게 브로드캐스트"""
        msg = json.dumps({"type": "telemetry", "data": data})
        disconnected = set()
        for client in self.active_clients:
            try:
                await client.send_text(msg)
            except Exception:
                disconnected.add(client)
        for client in disconnected:
            await self.disconnect_client(client)

    async def broadcast_status(self, msg: str):
        """상태 메시지를 모든 웹 클라이언트에게 브로드캐스트"""
        payload = json.dumps({"type": "status", "msg": msg, "timestamp": datetime.now().isoformat()})
        disconnected = set()
        for client in self.active_clients:
            try:
                await client.send_text(payload)
            except Exception:
                disconnected.add(client)
        for client in disconnected:
            await self.disconnect_client(client)

    async def send_command_to_drone(self, cmd: Dict[str, Any]) -> bool:
        """웹 클라이언트 명령을 드론으로 전송"""
        if self.drone_connection is None:
            return False
        try:
            await self.drone_connection.send_text(json.dumps(cmd))
            return True
        except Exception as e:
            logger.error(f"드론 전송 실패: {e}")
            return False


manager = ConnectionManager()


# ─── WebSocket 엔드포인트 ───────────────────────────────────
@app.websocket("/ws/drone")
async def websocket_drone(websocket: WebSocket):
    """
    Jetson 드론 클라이언트 연결.
    드론은 주기적으로 telemetry 메시지를 전송하고, 명령을 수신.
    """
    await manager.connect_drone(websocket)
    try:
        while True:
            data_str = await websocket.receive_text()
            msg = json.loads(data_str)

            if msg.get("type") == "telemetry":
                # 드론 상태 업데이트 + 모든 웹 클라이언트에게 브로드캐스트
                drone_state.update(msg.get("data", {}))
                await manager.broadcast_telemetry(drone_state)
                logger.info(f"Telemetry: lat={drone_state.get('lat'):.4f}, lon={drone_state.get('lon'):.4f}, alt={drone_state.get('alt'):.1f}m, battery={drone_state.get('battery')}%")

    except WebSocketDisconnect:
        await manager.disconnect_drone()
    except Exception as e:
        logger.exception(f"드론 연결 오류: {e}")
        await manager.disconnect_drone()


@app.websocket("/ws/client")
async def websocket_client(websocket: WebSocket):
    """
    웹 클라이언트 연결.
    클라이언트는 드론 상태를 수신하고, 명령(arm/disarm/takeoff/land/waypoint)을 전송.
    """
    await manager.connect_client(websocket)
    # 연결 직후 현재 드론 상태 전송
    await websocket.send_text(json.dumps({"type": "telemetry", "data": drone_state}))

    try:
        while True:
            data_str = await websocket.receive_text()
            msg = json.loads(data_str)

            if msg.get("type") == "command":
                # 명령을 드론으로 전송
                success = await manager.send_command_to_drone(msg)
                if success:
                    await websocket.send_text(json.dumps({"type": "status", "msg": f"명령 전송: {msg.get('cmd')}"}))
                else:
                    await websocket.send_text(json.dumps({"type": "status", "msg": "드론 연결 불가"}))

    except WebSocketDisconnect:
        await manager.disconnect_client(websocket)
    except Exception as e:
        logger.exception(f"클라이언트 오류: {e}")
        await manager.disconnect_client(websocket)


# ─── HTTP 기본 라우트 ────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "WebSocket 서버 실행 중", "drone_state": drone_state}


@app.get("/health")
async def health():
    return {"status": "ok", "drone_connected": drone_state.get("connected", False)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
