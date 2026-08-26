"""
command_receiver.py  (★★★ 2026-08-18 스펙 전면 재작성 ★★★)

서버-드론 통신 스펙 (drone_communication_spec_최종_.md, 2026-08-18 기준)
+ jetson_client_migration_guide.md 반영.

★★★ 안전 관련 핵심 변경 (반드시 숙지) ★★★
  구버전: CANCEL_PATROL = Kill Switch (즉시 모터차단)
  신버전: CANCEL_PATROL = 호버링+경로초기화 (모터 안 끔)
          EMERGENCY_STOP(신설) = 진짜 Kill Switch
  → 절대 혼동 금지. 관제사가 "순찰 취소"를 눌렀는데 드론이
    추락하는 사고를 막기 위한 변경.

연결 방식 (2026-08-17/18 변경):
  - SockJS 완전히 제거됨. 순수 WebSocket으로 /ws 직결.
  - 서버 자체(8080, HTTPS)에 직접 붙을 땐 wss:// + 자체서명 인증서 무시.
  - nginx(8031) 경유 시엔 ws://(평문) — nginx가 내부에서 TLS로 프록시.
  - 이 파일은 지금까지 8031(nginx) 경유로 운용해왔으므로 ws:// 사용.
  - STOMP CONNECT 프레임에 X-Device-Key 헤더 필요
    (서버 운영자에게 실제 키 발급받아 DEVICE_KEY 환경변수로 주입할 것.
     비어있으면 일단 브라우저 연결처럼 통과되나, 값이 있는데 틀리면
     거부됨 -> 반드시 정확한 값이거나 아예 비워둘 것).

구독 채널 (2026-08-16/8-6 변경):
  구: /topic/commands (공용, payload의 droneId로 드론이 직접 필터링)
  신: /topic/drones/{droneId}/commands (드론별 전용 채널,
      이미 자기 채널만 구독하므로 payload droneId 재필터링 불필요.
      단, 안전하게 한번 더 확인하는 코드는 유지함)

액션 10종 (2026-08-17 정렬):
  START_PATROL, RESUME_PATROL, PAUSE_PATROL(구 STOP류),
  CANCEL_PATROL(★의미변경, 더는 kill 아님), RETURN_TO_STATION(구 RETURN_TO_BASE),
  LAND(신설, 구 LAND_PATROL 자리), EMERGENCY_STOP(신설, 진짜 kill),
  SET_ROUTE(구 ROUTE_UPDATE), SET_STATION(구 STATION_UPDATE), PLAY_AUDIO

상태 전이 (내부에서 _status로 추적, 텔레메트리 status 필드에도 반영):
  IDLE/PAUSED --START_PATROL--> PATROLLING (항상 처음부터)
  PATROLLING --PAUSE_PATROL--> PAUSED (경로 보존)
  PAUSED/RETURNING --RESUME_PATROL--> PATROLLING (중단 지점부터)
  PATROLLING/PAUSED --CANCEL_PATROL--> PAUSED (경로 초기화, 착륙안함)
  PATROLLING/PAUSED --RETURN_TO_STATION--> RETURNING (순찰경로 보존)
  RETURNING --PAUSE_PATROL--> PAUSED (경로 보존)
  RETURNING --(스테이션도착)--> PAUSED, currentAction=RETURN_COMPLETE (착륙안함)
  PATROLLING --(경로완주)--> PAUSED, currentAction=PATROL_COMPLETE (착륙안함)
  공중 --LAND--> LANDING --(하강완료)--> IDLE
  공중 --EMERGENCY_STOP--> IDLE (즉시 kill)

★자동착륙 폐지(2026-08-17): 경로완주/스테이션도착 시 착륙하지 않고
  호버링 유지. currentAction으로 PATROL_COMPLETE/RETURN_COMPLETE를
  텔레메트리에 실어 서버에 알림 (이 파일은 명령수신 전용이라, 실제
  currentAction 전송은 telemetry_sender.py쪽 작업 - 상태 공유는
  status_state.json 파일을 통해 간접 연동함, 아래 StatusBridge 참고).

PLAY_AUDIO에 eventId 포함(2026-08-17 신규) -> 재생완료 후
  POST /events/{eventId}/broadcast-complete 콜백 호출 필요.

사전 실행 필요 (독립 프로세스, 계속 켜둘 것 - start_all.sh 사용 시 자동):
  /usr/local/lib/python3.8/dist-packages/mavsdk/bin/mavsdk_server \
    -p 50051 serial:///dev/pixhawk:115200
"""

import os
import json
import time
import base64
import tempfile
import subprocess
import asyncio
import logging
import threading
from urllib.parse import urlparse
from typing import Optional, List, Dict

import stomp
import websocket
import requests
from mavsdk import System

from waypoint_mission import WaypointMissionController

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("command_receiver")

# ─── 서버/드론 식별 설정 ────────────────────────────────────────
MY_SYSID = os.environ.get("DRONE_SYSID", "DR-01")  # droneId (문자열, DB 등록값과 정확히 일치해야 함)
DEVICE_KEY = os.environ.get("DEVICE_KEY", "")       # STOMP CONNECT X-Device-Key. 서버 운영자에게 발급받을 것

SERVER_URL = os.environ.get("SERVER_URL", "http://203.249.90.3:8031")
WS_ENDPOINT = "/ws"   # ★2026-08-18: SockJS 제거, 순수 WebSocket 단일 엔드포인트
BROADCAST_COMPLETE_URL_TMPL = SERVER_URL + "/events/{event_id}/broadcast-complete"

DEFAULT_ALTITUDE = float(os.environ.get("PATROL_ALTITUDE", "30.0"))
DEFAULT_SPEED = float(os.environ.get("PATROL_SPEED", "5.0"))
ACTION_TIMEOUT_SEC = 15.0
EMERGENCY_STOP_TIMEOUT_SEC = 5.0   # EMERGENCY_STOP(진짜 kill)용 - 최대한 빨리 반응

# ★2026-08-21: 배터리 자율복귀 페일세이프 (서버 경고 60%, 드론 자율복귀 40%)
BATTERY_RTL_THRESHOLD_PERCENT = float(os.environ.get("BATTERY_RTL_THRESHOLD", "40.0"))
STATION_ARRIVAL_RADIUS_M = 5.0

parsed = urlparse(SERVER_URL)
host = parsed.hostname
port = parsed.port or 80
ws_scheme = "wss" if parsed.scheme == "https" else "ws"
FORCE_WS_URI = f"{ws_scheme}://{host}:{port}{WS_ENDPOINT}"

# --- 몽키패치: URL을 /ws(순수 WebSocket, SockJS 아님)로 강제 override ---
# ★2026-08-18: 서버가 SockJS를 완전히 제거하고 /ws 단일 엔드포인트로
# 통일됨. stomp.py 라이브러리가 내부적으로 계산하는 URL이 우리 의도와
# 다를 수 있어(라이브러리 버전에 따라 SockJS 서브패스를 붙이려 시도할
# 가능성), 검증된 방식(이전 세션에 실기 확인됨)인 websocket.create_connection
# 몽키패치로 URL을 명시적으로 고정한다. HTTPS(자체서명)로 직접 붙는
# 경우를 대비해 SSL 검증 무시도 유지.
_original_create_connection = websocket.create_connection

def _patched_create_connection(url, *args, **kwargs):
    logger.info(f"[STOMP-Patch] Overriding URL: {url} -> {FORCE_WS_URI}")
    if kwargs.get('sslopt') is None:
        kwargs['sslopt'] = {}
    import ssl as _ssl
    kwargs['sslopt']['cert_reqs'] = _ssl.CERT_NONE
    return _original_create_connection(FORCE_WS_URI, *args, **kwargs)

websocket.create_connection = _patched_create_connection

# 상태 공유 파일 (telemetry_sender.py가 읽어서 status/currentAction 반영)
STATUS_STATE_PATH = os.environ.get("STATUS_STATE_PATH", "/tmp/drone_status_state.json")

# ★2026-08-21: 요청기반 스트리밍 (REQUEST_STREAM/STOP_STREAM)
# main.py(카메라 프로세스)가 별도로 이 파일을 주기적으로 읽어
# MJPEG 스트리밍 서버를 켜고 끈다 (프로세스가 분리되어 있어 파일로 신호전달)
STREAM_REQUEST_STATE_PATH = os.environ.get("STREAM_REQUEST_STATE_PATH", "/tmp/drone_stream_request.json")

# ★2026-08-21 서버 확정 스펙: 프레임은 HTTP(POST /drones/{droneId}/stream/frame)로
# 원본 JPEG 바이너리 전송(base64 아님). REQUEST_STREAM이 값을 안 주면 아래 기본값 사용.
STREAM_DEFAULT_FPS = 5
STREAM_DEFAULT_WIDTH = 640
STREAM_DEFAULT_HEIGHT = 480
STREAM_DEFAULT_QUALITY = 70


def play_tts_audio_base64(b64_audio: str, event_id: Optional[int] = None) -> None:
    """
    STOMP PLAY_AUDIO의 audioBase64를 디코딩해 wav 저장 후 aplay 재생.
    재생 완료 후 eventId가 있으면 방송완료 콜백을 호출한다(2026-08-17 신규).
    """
    path = None
    try:
        audio_bytes = base64.b64decode(b64_audio)
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="tts_")
        os.close(fd)
        with open(path, "wb") as f:
            f.write(audio_bytes)
        logger.info(f"🔊 TTS 재생 시작: {path} ({len(audio_bytes)} bytes)")
        subprocess.run(["aplay", path], check=True)
        logger.info("✅ TTS 재생 완료")

        if event_id is not None:
            try:
                url = BROADCAST_COMPLETE_URL_TMPL.format(event_id=event_id)
                headers = {"X-Device-Key": DEVICE_KEY} if DEVICE_KEY else {}
                resp = requests.post(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    logger.info(f"📢 방송완료 콜백 성공 (eventId={event_id})")
                else:
                    logger.warning(f"방송완료 콜백 실패 (status={resp.status_code}, eventId={event_id})")
            except Exception as e:
                logger.warning(f"방송완료 콜백 오류: {e}")
        else:
            logger.debug("eventId 없음 - 방송완료 콜백 생략 (구버전 명령 호환)")
    except Exception as e:
        logger.error(f"TTS 재생 실패: {e}")
    finally:
        if path is not None:
            try:
                os.remove(path)
            except Exception:
                pass


class DroneCommandHandler:
    """MAVSDK 드론 제어. STOMP(동기,별도스레드)에서 dispatch() 호출 -> asyncio로 넘김."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.system: Optional[System] = None
        self.mission: Optional[WaypointMissionController] = None
        self._route: List[Dict[str, float]] = []          # 순찰 웨이포인트 (SET_ROUTE)
        self._station: Optional[Dict[str, float]] = None  # 귀환 스테이션 좌표 (SET_STATION), 경로와 별도 보관
        self._status: str = "IDLE"  # IDLE/PATROLLING/PAUSED/RETURNING/LANDING (텔레메트리 status와 동기화용)
        self._watch_task: Optional[asyncio.Task] = None  # 완주/도착 감지 백그라운드 태스크
        self._battery_rtl_triggered: bool = False  # 배터리 자율복귀 중복트리거 방지 플래그 (SET_ROUTE 정의 이후 사용)

    async def connect(self):
        self.system = System(mavsdk_server_address="localhost", port=50051)
        logger.info("공유 mavsdk_server(localhost:50051)에 연결 시도")
        await self.system.connect()
        await asyncio.sleep(2.0)
        self.mission = WaypointMissionController(self.system)
        logger.info("✅ 드론 연결 성공")

    def start_battery_watch(self):
        """
        ★2026-08-21 신규: 배터리 자율복귀 페일세이프.
        STOMP 연결/서버 통신 여부와 완전히 무관하게, MAVSDK 배터리
        스트림을 직접 구독해 상시 감시한다 (같은 프로세스 내 asyncio
        태스크라 통신 두절 중에도 그대로 동작함 - 서버팀 요청사항
        "두절 중에도 배터리 페일세이프는 동작해야 한다"를 만족).
        비행중(IDLE 아님) 상태에서 배터리가 임계값 이하로 떨어지면
        단 1회만 자율복귀를 트리거한다(_battery_rtl_triggered 플래그).
        """
        asyncio.create_task(self._battery_watch_loop())

    async def _battery_watch_loop(self):
        try:
            async for battery in self.system.telemetry.battery():
                # ★2026-08-26: MAVSDK battery.remaining_percent 스펙은 항상 0.0~1.0
                # fraction (공식 문서 기준). 예전엔 "이미 0~100으로 온 경우" 대비
                # `if pct <= 1.0: pct *= 100` 방어코드가 있었으나, 이건 원래
                # 코드 다른 곳의 이중곱셈 버그(9900% 사고, 2026-07-18) 땜질이었고
                # 배터리가 진짜 1% 미만으로 위급한 상황을 "이미 변환된 값"으로
                # 오판해 RTL 페일세이프가 트리거 안 될 수 있는 위험이 있었음.
                # 스펙대로 항상 고정 변환.
                pct = battery.remaining_percent * 100.0

                if (
                    pct <= BATTERY_RTL_THRESHOLD_PERCENT
                    and not self._battery_rtl_triggered
                    and self._status not in ("IDLE", "LANDING")
                ):
                    logger.warning(
                        f"🔋 배터리 {pct:.1f}% <= 임계값({BATTERY_RTL_THRESHOLD_PERCENT}%) "
                        f"- 자율 복귀(BATTERY_RTL) 트리거"
                    )
                    self._battery_rtl_triggered = True
                    asyncio.create_task(self._battery_rtl())
        except Exception as e:
            logger.error(f"배터리 감시 오류: {e}")

    async def _battery_rtl(self):
        """
        배터리 부족 자율복귀. RETURN_TO_STATION(관제사 지시, 도착 후
        호버링)과 달리, 이 경로는 도착 후 반드시 착륙까지 수행한다
        (2026-08-21 서버팀 확정사항 - 호버링만 하면 나머지 배터리를
        마저 쓰고 추락하므로).
        """
        if not (self._station and self._station.get("lat") is not None):
            logger.error(
                "🔋 배터리 자율복귀 필요하지만 스테이션(SET_STATION) 미설정 "
                "- 복귀 불가! 즉시 hold()만 시도"
            )
            try:
                await self.system.action.hold()
            except Exception as e:
                logger.error(f"비상 hold() 실패: {e}")
            return

        try:
            self._cancel_watch_task()
            self._status = "RETURNING"
            self._write_status_state(current_action="BATTERY_RTL")
            logger.warning(
                f"🔋 배터리 자율복귀 비행 시작 -> 스테이션 lat={self._station['lat']}, "
                f"lon={self._station['lon']} (도착 후 착륙까지 수행)"
            )
            ok = await self.mission.upload_and_start(
                [{"lat": self._station["lat"], "lon": self._station["lon"], "alt": DEFAULT_ALTITUDE}],
                altitude=DEFAULT_ALTITUDE, speed=DEFAULT_SPEED,
            )
            if ok:
                self._watch_task = asyncio.create_task(
                    self.mission.wait_for_arrival(
                        self._station["lat"], self._station["lon"],
                        radius_m=STATION_ARRIVAL_RADIUS_M,
                        on_arrival=self._on_battery_rtl_arrival,
                    )
                )
            else:
                logger.error("🔋 배터리 자율복귀 비행 시작 실패")
        except Exception as e:
            logger.error(f"❌ 배터리 자율복귀 실패: {e}")

    def _on_battery_rtl_arrival(self):
        """배터리 자율복귀 도착 콜백 - RETURN_TO_STATION과 달리 착륙까지 진행."""
        logger.warning("🔋 배터리 자율복귀 스테이션 도착 - 착륙 시작 (호버링하지 않음)")
        asyncio.create_task(self._land())

    def _write_status_state(self, current_action: Optional[str] = None):
        """telemetry_sender.py가 읽어갈 상태 공유 파일 갱신."""
        try:
            with open(STATUS_STATE_PATH, "w") as f:
                json.dump({"status": self._status, "currentAction": current_action}, f)
        except Exception as e:
            logger.debug(f"상태 공유 파일 쓰기 실패: {e}")

    def _set_stream_request(self, enabled: bool, cmd_data: Optional[dict] = None):
        """
        ★2026-08-21 신규, ★2026-08-22 서버스펙 확정 반영: REQUEST_STREAM/
        STOP_STREAM 처리. main.py(별도 프로세스)가 이 파일을 주기적으로
        읽어 스트리밍 업로드 루프를 켜고 끈다. command_receiver.py 자체는
        카메라나 HTTP 업로드에 접근하지 않고, 단지 신호만 남긴다.

        서버 확정 스펙(2026-08-21 회신):
          - 영상은 STOMP가 아니라 HTTP(POST /drones/{droneId}/stream/frame)
          - streamId를 매 업로드마다 X-Stream-Id 헤더로 그대로 돌려줘야 함
            (관제사가 껐다 켜면 옛 세션 프레임이 새 세션에 섞이는 것 방지)
          - uploadPath/fps/width/height/quality는 REQUEST_STREAM이 실어줌
            (없으면 기본값 640x480/5fps/q70 - 서버가 재빌드 없이 조정 가능)
        """
        cmd_data = cmd_data or {}
        try:
            state = {
                "stream_enabled": enabled,
                "ts": time.time(),
                "stream_id": cmd_data.get("streamId"),
                "upload_path": cmd_data.get("uploadPath"),
                "fps": cmd_data.get("fps", STREAM_DEFAULT_FPS),
                "width": cmd_data.get("width", STREAM_DEFAULT_WIDTH),
                "height": cmd_data.get("height", STREAM_DEFAULT_HEIGHT),
                "quality": cmd_data.get("quality", STREAM_DEFAULT_QUALITY),
            }
            with open(STREAM_REQUEST_STATE_PATH, "w") as f:
                json.dump(state, f)
            logger.info(
                f"📹 {'REQUEST_STREAM' if enabled else 'STOP_STREAM'} -> "
                f"stream_enabled={enabled}, streamId={state['stream_id']}"
            )
        except Exception as e:
            logger.warning(f"스트리밍 요청 상태 파일 쓰기 실패: {e}")

    def _cancel_watch_task(self):
        """완주/도착 감지 백그라운드 태스크가 살아있으면 취소.
        새로운 상태전이(다른 명령)가 발생할 때마다 반드시 호출해야
        오래된 감지결과가 최신 상태를 덮어쓰는 사고를 막을 수 있다."""
        if self._watch_task is not None and not self._watch_task.done():
            self._watch_task.cancel()
        self._watch_task = None

    def _on_patrol_complete(self):
        """미션 완주 콜백 (mission.wait_for_mission_complete에서 호출됨).
        자동착륙 폐지 규정: 착륙하지 않고 호버링 유지, currentAction으로
        서버에 완주 사실을 통지한다."""
        self._status = "PAUSED"
        self._write_status_state(current_action="PATROL_COMPLETE")
        logger.info("✅ PATROL_COMPLETE 통지 (호버링 유지, 착륙안함)")

    def _on_station_arrival(self):
        """스테이션 도착 콜백 (mission.wait_for_arrival에서 호출됨)."""
        self._status = "PAUSED"
        self._write_status_state(current_action="RETURN_COMPLETE")
        logger.info("✅ RETURN_COMPLETE 통지 (호버링 유지, 착륙안함)")

    def dispatch(self, cmd_data: dict):
        """STOMP 스레드에서 호출됨 -> asyncio 루프에 코루틴 제출."""
        # 채널 자체가 자기 droneId 전용이라 필터링은 원칙적으로 불필요하지만,
        # 안전을 위해 payload에 droneId가 있으면 한 번 더 확인
        target_id = cmd_data.get("droneId")
        if target_id is not None and target_id != MY_SYSID:
            logger.debug(f"다른 드론({target_id}) 대상 명령 무시 (나: {MY_SYSID})")
            return

        action = cmd_data.get("action")
        route = cmd_data.get("route")
        logger.info(f"📥 명령 수신: {action} (대상: {target_id or '전체'})")

        if action == "START_PATROL":
            asyncio.run_coroutine_threadsafe(self._start_patrol(), self.loop)
        elif action == "RESUME_PATROL":
            asyncio.run_coroutine_threadsafe(self._resume_patrol(), self.loop)
        elif action == "PAUSE_PATROL":
            asyncio.run_coroutine_threadsafe(self._pause_patrol(), self.loop)
        elif action == "CANCEL_PATROL":
            asyncio.run_coroutine_threadsafe(self._cancel_patrol(), self.loop)
        elif action == "RETURN_TO_STATION":
            asyncio.run_coroutine_threadsafe(self._return_to_station(), self.loop)
        elif action == "LAND":
            asyncio.run_coroutine_threadsafe(self._land(), self.loop)
        elif action == "EMERGENCY_STOP":
            asyncio.run_coroutine_threadsafe(self._emergency_stop(), self.loop)
        elif action == "SET_ROUTE":
            asyncio.run_coroutine_threadsafe(self._set_route(route or []), self.loop)
        elif action == "SET_STATION":
            station = cmd_data.get("station", {})
            # ★2026-08-21: 서버가 경도 키를 lng->lon으로 통일함
            self._station = {"lat": station.get("lat"), "lon": station.get("lon")}
            logger.info(f"🏠 SET_STATION: 스테이션 좌표 저장 lat={self._station['lat']}, lon={self._station['lon']}")
        elif action == "REQUEST_STREAM":
            self._set_stream_request(True, cmd_data)
        elif action == "STOP_STREAM":
            self._set_stream_request(False, cmd_data)
        elif action == "PLAY_AUDIO":
            audio_b64 = cmd_data.get("audioBase64")
            event_id = cmd_data.get("eventId")
            if audio_b64:
                threading.Thread(
                    target=play_tts_audio_base64, args=(audio_b64, event_id), daemon=True
                ).start()
            else:
                logger.warning("PLAY_AUDIO 명령에 audioBase64 필드 없음")
        else:
            logger.warning(f"❓ 알 수 없는 action: {action}")

    # ─── 비행 제어 액션들 ────────────────────────────────────────

    async def _start_patrol(self):
        """IDLE/PAUSED에서만 수락. 항상 경로를 처음부터 돈다."""
        if self._status not in ("IDLE", "PAUSED"):
            logger.warning(f"START_PATROL: 현재 상태({self._status})에서는 무시 (IDLE/PAUSED만 수락)")
            return
        try:
            logger.info("🚀 START_PATROL 실행 (지상/일시정지 -> 처음부터 순찰)")
            if self._route:
                logger.info(f"저장된 경로 {len(self._route)}개 지점으로 순찰 비행 시작")
                ok = await asyncio.wait_for(
                    self.mission.upload_and_start(
                        self._route, altitude=DEFAULT_ALTITUDE, speed=DEFAULT_SPEED
                    ), timeout=ACTION_TIMEOUT_SEC * 2
                )
                if ok:
                    self._status = "PATROLLING"
                    self._write_status_state()
                    self._cancel_watch_task()
                    self._watch_task = asyncio.create_task(
                        self.mission.wait_for_mission_complete(self._on_patrol_complete)
                    )
                logger.info(f"미션 비행 {'시작됨' if ok else '실패'}")
            else:
                # ★2026-08-25 진단강화: 경로가 비어있으면 관제사 의도(순찰)와
                # 다르게 "제자리 이륙"만 하게 됨. SET_ROUTE가 아직 도착 안했거나
                # 처리 순서가 꼬인 경합(race condition) 가능성이 높은 상황이라
                # 반드시 눈에 띄게 경고로 남긴다 (2026-08-25 실기에서 이 경로로
                # 빠져 2m 남짓한 저고도 호버링만 지속된 사례 있었음).
                logger.warning(
                    "⚠️ START_PATROL: 저장된 경로(_route)가 비어있음! "
                    "SET_ROUTE가 아직 도착 전이거나 순서가 꼬였을 가능성 - "
                    "제자리 이륙만 수행됨 (의도한 순찰 비행이 아닐 수 있음)"
                )
                async for is_armed in self.system.telemetry.armed():
                    if not is_armed:
                        logger.info("드론 무장 시도...")
                        await asyncio.wait_for(self.system.action.arm(), timeout=ACTION_TIMEOUT_SEC)
                    break
                logger.info("이륙 시도... (경로 없음, 제자리 비행)")
                await asyncio.wait_for(self.system.action.takeoff(), timeout=ACTION_TIMEOUT_SEC)
                self._status = "PATROLLING"
                self._write_status_state()
        except asyncio.TimeoutError:
            logger.error(f"⏱️ START_PATROL 타임아웃")
        except Exception as e:
            logger.exception(f"❌ START_PATROL 실패: {e}")

    async def _resume_patrol(self):
        """PAUSED/RETURNING에서 수락. 중단 지점부터 이어서 순찰."""
        if self._status not in ("PAUSED", "RETURNING"):
            logger.warning(f"RESUME_PATROL: 현재 상태({self._status})에서는 무시 (PAUSED/RETURNING만 수락)")
            return
        if not self._route:
            logger.warning("RESUME_PATROL: 저장된 경로 없음 - 재개 불가")
            return
        try:
            logger.info("▶️ RESUME_PATROL 실행 (호버링/복귀중단 -> 저장경로로 재개)")
            ok = await asyncio.wait_for(
                self.mission.upload_and_start(
                    self._route, altitude=DEFAULT_ALTITUDE, speed=DEFAULT_SPEED
                ), timeout=ACTION_TIMEOUT_SEC * 2
            )
            if ok:
                self._status = "PATROLLING"
                self._write_status_state()
                self._cancel_watch_task()
                self._watch_task = asyncio.create_task(
                    self.mission.wait_for_mission_complete(self._on_patrol_complete)
                )
            logger.info(f"재개 비행 {'시작됨' if ok else '실패'}")
        except asyncio.TimeoutError:
            logger.error(f"⏱️ RESUME_PATROL 타임아웃")
        except Exception as e:
            logger.error(f"❌ RESUME_PATROL 실패: {e}")

    async def _pause_patrol(self):
        """비행 중 -> 현재 위치에서 호버링. 경로는 보존."""
        try:
            logger.info("🛑 PAUSE_PATROL -> 호버링 (경로 보존)")
            await asyncio.wait_for(self.system.action.hold(), timeout=ACTION_TIMEOUT_SEC)
            self._cancel_watch_task()
            self._status = "PAUSED"
            self._write_status_state()
        except asyncio.TimeoutError:
            logger.error(f"⏱️ PAUSE_PATROL 타임아웃")
        except Exception as e:
            logger.error(f"❌ PAUSE_PATROL 실패: {e}")

    async def _cancel_patrol(self):
        """
        ★★★ 2026-08-17 의미 변경: 더 이상 Kill Switch가 아니다 ★★★
        즉각 호버링 + 경로 초기화. 착륙하지 않고 모터도 끄지 않는다.
        (예전 버전은 여기서 action.kill()을 호출했으나, 그러면 관제사가
        "순찰 취소"를 눌렀을 때 실제로는 드론이 추락하는 심각한 안전
        문제가 있었음. 진짜 kill switch는 EMERGENCY_STOP으로 분리됨)
        """
        try:
            logger.info("🚫 CANCEL_PATROL 실행 (호버링 + 경로초기화, 모터 유지)")
            await asyncio.wait_for(self.system.action.hold(), timeout=ACTION_TIMEOUT_SEC)
            self._cancel_watch_task()
            self._route = []
            self._status = "PAUSED"
            self._write_status_state()
            try:
                await asyncio.wait_for(self.mission.clear_mission(), timeout=ACTION_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                logger.warning("미션 초기화 타임아웃 (호버링은 이미 완료됨)")
        except asyncio.TimeoutError:
            logger.error(f"⏱️ CANCEL_PATROL 타임아웃")
        except Exception as e:
            logger.error(f"❌ CANCEL_PATROL 실패: {e}")

    async def _return_to_station(self):
        """
        PATROLLING/PAUSED -> RETURNING. 순찰 경로(self._route)는
        절대 지우지 않는다 (2026-08-14 규약) - RESUME_PATROL로 복귀를
        중단하고 원래 순찰로 되돌아갈 수 있어야 하므로.
        """
        # ★2026-08-25 진단강화: 진입 시점의 상태를 반드시 남긴다.
        # 2026-08-25 실기에서 복귀 버튼을 눌러도 제자리에 계속 머무는
        # 원인불명 사례가 있었음 - 다음 재현시 self._station/self._status가
        # 어떤 값이었는지부터 확인할 수 있어야 한다.
        logger.info(
            f"RETURN_TO_STATION 진입: 현재상태={self._status}, "
            f"저장된스테이션={self._station}"
        )
        try:
            if self._station and self._station.get("lat") is not None:
                logger.info(f"🏠 RETURN_TO_STATION 실행: 스테이션으로 귀환 lat={self._station['lat']}, lon={self._station['lon']} (순찰경로 보존)")
                # 순찰 경로(self._route)는 그대로 두고, 스테이션 좌표로만 별도 비행
                ok = await asyncio.wait_for(
                    self.mission.upload_and_start(
                        [{"lat": self._station["lat"], "lon": self._station["lon"], "alt": DEFAULT_ALTITUDE}],
                        altitude=DEFAULT_ALTITUDE, speed=DEFAULT_SPEED
                    ), timeout=ACTION_TIMEOUT_SEC * 2
                )
                if ok:
                    self._status = "RETURNING"
                    self._write_status_state()
                    self._cancel_watch_task()
                    self._watch_task = asyncio.create_task(
                        self.mission.wait_for_arrival(
                            self._station["lat"], self._station["lon"],
                            radius_m=5.0, on_arrival=self._on_station_arrival,
                        )
                    )
                else:
                    logger.error(
                        "❌ RETURN_TO_STATION: upload_and_start()가 False 반환 "
                        "- mission.py 내부 로그(미션 업로드/시작 실패)를 확인할 것"
                    )
                logger.info(f"귀환 비행 {'시작됨' if ok else '실패'} (도착해도 착륙하지 않고 호버링 대기)")
            else:
                logger.warning(
                    f"RETURN_TO_STATION: 저장된 스테이션 좌표 없음(self._station={self._station}) "
                    f"- PX4 기본 RTL로 대체"
                )
                await asyncio.wait_for(self.system.action.return_to_launch(), timeout=ACTION_TIMEOUT_SEC)
                self._status = "RETURNING"
                self._write_status_state()
        except asyncio.TimeoutError:
            logger.error(
                f"⏱️ RETURN_TO_STATION 타임아웃 (상태={self._status}, 스테이션={self._station})"
            )
        except Exception as e:
            logger.exception(f"❌ RETURN_TO_STATION 실패: {e}")

    async def _land(self):
        """
        신설(구 LAND_PATROL 자리, 미구현이었음). 공중 -> 현재위치에서
        안전하게 하강 착륙. 자동착륙 폐지 이후, 착륙은 오직 이 명령을
        받았을 때만 수행한다.
        """
        try:
            logger.info("🛬 LAND 실행 (현재위치 하강 착륙)")
            self._cancel_watch_task()
            self._status = "LANDING"
            self._write_status_state()
            await asyncio.wait_for(self.system.action.land(), timeout=ACTION_TIMEOUT_SEC)
            # 하강 완료 감지는 in_air 폴링으로 처리.
            # ★2026-08-26: 이 감시 태스크를 self._watch_task에 저장해
            # _cancel_watch_task()로 취소 가능하게 함. 기존엔 참조가
            # 어디에도 남지 않아, LAND 도중 다른 명령(예: CANCEL_PATROL)이
            # 들어와 상태가 바뀌어도 이 태스크가 계속 살아있다가, 나중에
            # 실제 in_air=False 시점에 self._status를 묻지도 않고 "IDLE"로
            # 강제 덮어써서 텔레메트리 상태가 꼬일 수 있었음(다른 완주/도착
            # 감지 태스크와 달리 이것만 추적이 안 되고 있었음). 상태가
            # 여전히 LANDING일 때만 IDLE로 바꾸는 가드도 이중으로 추가.
            async def _wait_landed():
                try:
                    async for in_air in self.system.telemetry.in_air():
                        if not in_air:
                            if self._status == "LANDING":
                                self._status = "IDLE"
                                self._write_status_state()
                                logger.info("✅ 착륙 완료 (IDLE)")
                            else:
                                logger.info(
                                    f"착륙 완료 감지됐으나 상태가 이미 {self._status}로 "
                                    f"바뀌어 있어 IDLE 덮어쓰기 생략"
                                )
                            break
                except asyncio.CancelledError:
                    logger.debug("착륙 완료 감지 태스크 취소됨 (다른 명령으로 상태 전환)")
                    raise
            self._watch_task = asyncio.create_task(_wait_landed())
        except asyncio.TimeoutError:
            logger.error(f"⏱️ LAND 타임아웃")
        except Exception as e:
            logger.error(f"❌ LAND 실패: {e}")

    async def _emergency_stop(self):
        """
        ★★★ 진짜 Kill Switch (신설, 구 CANCEL_PATROL의 역할 승계) ★★★
        관제사 승인 하에, 고도와 무관하게 즉시 모터 차단.
        짧은 타임아웃(5초)으로 최대한 빨리 반응하도록 함.
        """
        try:
            logger.warning("🚨 EMERGENCY_STOP 실행 (즉시 kill - 관제사 승인된 강제정지)")
            try:
                await asyncio.wait_for(self.system.action.kill(), timeout=EMERGENCY_STOP_TIMEOUT_SEC)
                logger.info("✅ kill(강제disarm) 완료")
            except asyncio.TimeoutError:
                logger.error(f"⏱️ kill 타임아웃 ({EMERGENCY_STOP_TIMEOUT_SEC}s) - 응답 없음")
            self._cancel_watch_task()
            self._route = []
            self._status = "IDLE"
            self._write_status_state()
        except Exception as e:
            logger.error(f"❌ EMERGENCY_STOP 실패: {e}")

    async def _set_route(self, route: list):
        """
        새로운 순찰 웨이포인트 목록 저장만 한다 (신스펙: 자동 비행 시작 안 함).
        실제 비행은 START_PATROL/RESUME_PATROL이 별도로 트리거해야 함.

        ★2026-08-21 스펙: route가 [lat, lon] 배열이 아니라 객체 배열로
        변경됨: {"lat":.., "lon":.., "alt_agl":.., "ground_elevation_m":..(선택)}
        - lon (구 lng) 필드로 통일
        - alt_agl: 지면기준 목표고도. 관제사 미지정시 서버가 기본 50m를
          채워 보내지만, 혹시 누락되어 오면 여기서도 50m 기본값 적용
        - ground_elevation_m: 선택 필드, 당분간 안 옴(브이월드 연동 전)
        - 최소 안전고도(20m) 하한 적용은 waypoint_mission._build_mission_items
          에서 일괄 처리 (여기서는 원본 alt_agl 값을 그대로 저장)
        """
        try:
            self._route = [
                {
                    "lat": float(pt["lat"]),
                    "lon": float(pt["lon"]),
                    "alt": float(pt.get("alt_agl", 50.0)),
                }
                for pt in route
            ]
            logger.info(f"🗺️ SET_ROUTE: {len(self._route)}개 지점 저장 완료 (비행은 START_PATROL 대기)")
        except Exception as e:
            logger.error(f"❌ SET_ROUTE 실패: {e}")


class CommandListener(stomp.ConnectionListener):
    def __init__(self, handler: DroneCommandHandler):
        self.handler = handler

    def on_error(self, frame):
        logger.error(f"[STOMP] Error: {frame.body}")

    def on_message(self, frame):
        logger.info(f"[STOMP] Message: {frame.body}")
        try:
            cmd_data = json.loads(frame.body)
            self.handler.dispatch(cmd_data)
        except json.JSONDecodeError:
            logger.error("[STOMP] Invalid JSON")

    def on_disconnected(self):
        logger.warning("[STOMP] 연결 끊김")


def run_stomp(handler: DroneCommandHandler):
    """
    STOMP 연결 (동기, 별도 스레드에서 실행). 끊기면 재연결.
    ★2026-08-18: SockJS 완전 제거, 순수 WebSocket(/ws) 직결.
    """
    channel = f"/topic/drones/{MY_SYSID}/commands"  # ★2026-08-16: 드론별 전용 채널

    while True:
        try:
            logger.info(f"[STOMP] Connecting to {host}:{port} (forced URL: {FORCE_WS_URI}) ...")
            conn = stomp.WSStompConnection([(host, port)])
            conn.set_listener('', CommandListener(handler))

            connect_headers = {}
            if DEVICE_KEY:
                connect_headers["X-Device-Key"] = DEVICE_KEY

            conn.connect(wait=True, headers=connect_headers)
            logger.info("[STOMP] Connected!")
            conn.subscribe(destination=channel, id=1, ack='auto')
            logger.info(f"[STOMP] Subscribed to {channel}. Waiting for commands...")

            while conn.is_connected():
                time.sleep(1)
        except Exception as e:
            logger.error(f"[STOMP] 연결 오류: {e}")

        logger.info("⏳ 5초 후 STOMP 재연결...")
        time.sleep(5)


async def main():
    loop = asyncio.get_event_loop()
    handler = DroneCommandHandler(loop)
    await handler.connect()
    handler.start_battery_watch()  # ★2026-08-21: 배터리 자율복귀 페일세이프 상시 감시 시작

    t = threading.Thread(target=run_stomp, args=(handler,), daemon=True)
    t.start()

    logger.info("명령 수신기 가동 중 (Ctrl+C 종료)")
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    if not DEVICE_KEY:
        logger.warning("⚠️ DEVICE_KEY 환경변수가 비어있습니다. 서버 운영자에게 발급받아 설정할 것.")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 종료")
