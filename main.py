"""
main.py
CSI 카메라(GStreamer) -> RingBuffer -> 추론 -> 트리거 -> 영상전송 + 호버링

트리거(이상 감지) 시 동작:
  1. MAVSDK action.hold() 로 즉시 호버링 (제자리 정지)
  2. 영상을 서버(/analyze-video)로 전송
  3. 호버링 상태 유지 (재개는 command_receiver.py가 STOMP로 받는
     별도 명령으로 처리 예정 - 아직 서버와 재개 명령 형식 미정)

주의: detect_anomaly()는 아직 더미(0.0 고정). 실제 모델 연결 전까지
      트리거/호버링 자체는 강제 테스트로만 확인 가능.
"""

import os
import time
import logging
import signal
import sys
import asyncio
import threading
from typing import Optional
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
import requests
from mavsdk import System

from ring_buffer import RingBuffer, FPS, BUFFER_MAXLEN, INFER_WINDOW_LEN
from uploader import upload_clip_async, upload_clip_sync
from anomaly_model import AnomalyPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


# ─── 카메라 설정 ──────────────────────────────────────────────────
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
ANOMALY_THRESHOLD = 0.8     # 트리거 임계값 (모델 도입 후 튜닝 필요)
TRIGGER_COOLDOWN_SEC = 9    # 같은 클립을 중복 전송하지 않도록 쿨다운

# ─── 실시간 스트리밍 설정 (테스트/Tailscale 직결 전용) ─────────────
STREAM_ENABLED = os.environ.get("STREAM_ENABLED", "1") == "1"
STREAM_PORT = int(os.environ.get("STREAM_PORT", "8090"))
STREAM_JPEG_QUALITY = 80  # 0~100, 높을수록 고화질/고용량

# ★2026-08-21: 요청기반 스트리밍. command_receiver.py(별도 프로세스)가
# REQUEST_STREAM/STOP_STREAM 수신 시 이 파일에 신호를 남긴다.
STREAM_REQUEST_STATE_PATH = os.environ.get("STREAM_REQUEST_STATE_PATH", "/tmp/drone_stream_request.json")

# ★2026-08-21 서버 확정 스펙: 영상은 STOMP가 아니라 HTTP로 전송.
# (STOMP에 영상을 얹으면 EMERGENCY_STOP 등 제어명령이 영상 프레임
#  뒤에 큐잉되어 늦게 도착하는 안전문제가 있다는 서버팀 설명 반영)
SERVER_HOST = os.environ.get("SERVER_URL", "http://203.249.90.3:8031")
DEVICE_KEY = os.environ.get("DEVICE_KEY", "")
STREAM_FRAME_TIMEOUT_SEC = 5.0     # 프레임 1장 업로드 타임아웃
STREAM_NO_RESPONSE_LIMIT_SEC = 10.0  # 이 시간 무응답이면 자체 중지 (서버 확정 스펙)
MAVSDK_URI = "serial:///dev/pixhawk:115200"


def create_gstreamer_pipeline(width=CAMERA_WIDTH, height=CAMERA_HEIGHT, fps=FPS) -> str:
    """CSI 카메라용 GStreamer 파이프라인 문자열 생성."""
    return (
        f"nvarguscamerasrc sensor_id=0 sensor-mode=4 ! "
        f"video/x-raw(memory:NVMM), width={width}, height={height}, "
        f"format=NV12, framerate={fps}/1 ! "
        f"nvvidconv flip-method=0 ! "
        f"video/x-raw,format=BGRx ! "
        f"videoconvert ! "
        f"video/x-raw,format=BGR ! "
        f"appsink drop=true max-buffers=2"
    )


_anomaly_pipeline = None

def get_anomaly_pipeline() -> AnomalyPipeline:
    """AnomalyPipeline 지연 초기화 (엔진 로드는 최초 1회만)."""
    global _anomaly_pipeline
    if _anomaly_pipeline is None:
        _anomaly_pipeline = AnomalyPipeline()
    return _anomaly_pipeline


def detect_anomaly(window: np.ndarray) -> float:
    """
    YOLOv5n + WideBranchNet(Jigsaw-VAD) 실제 추론.
    window: (T,H,W,C) BGR uint8, T=9 (1초, ring_buffer INFER_WINDOW_SECONDS=1)
    반환: anomaly_score 0.0~1.0 (높을수록 이상)
    """
    try:
        pipeline = get_anomaly_pipeline()
        return pipeline.compute_score(window)
    except Exception as e:
        logger.error(f"모델 추론 실패: {e}")
        return 0.0  # 추론 실패 시 안전하게 정상으로 처리 (오탐 방지)


class DroneHoverController:
    """
    MAVSDK 연결 + 호버링 전담. 별도 스레드에서 asyncio 이벤트 루프 실행.
    main 캡처 루프(동기)에서 hover_now() 호출 시 스레드 안전하게 처리.
    """

    def __init__(self):
        self.system: Optional[System] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._ready = threading.Event()
        self._is_hovering = False

    def start(self):
        """백그라운드 스레드에서 asyncio 루프 + MAVSDK 연결 시작."""
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()
        self._ready.wait(timeout=15.0)

    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._connect())
        self._ready.set()
        self.loop.run_forever()

    async def _connect(self):
        try:
            # 공유 mavsdk_server(포트 50051)에 접속 - 시리얼 포트 독점 문제 해결
            self.system = System(mavsdk_server_address="localhost", port=50051)
            logger.info("[Hover] 공유 mavsdk_server(localhost:50051)에 연결 시도")
            await self.system.connect()
            await asyncio.sleep(2.0)
            logger.info("[Hover] ✅ 드론 연결 성공")
        except Exception as e:
            logger.error(f"[Hover] ❌ 드론 연결 실패: {e}")
            self.system = None

    async def _hold(self):
        try:
            await self.system.action.hold()
            self._is_hovering = True
            logger.info("[Hover] 🛑 호버링 실행 (action.hold)")
        except Exception as e:
            logger.error(f"[Hover] ❌ 호버링 실패: {e}")

    def hover_now(self):
        """동기 캡처 루프에서 호출. 호버링 코루틴을 asyncio 루프에 제출."""
        if not self.system or not self.loop:
            logger.warning("[Hover] 드론 미연결 상태 - 호버링 스킵")
            return
        if self._is_hovering:
            return  # 이미 호버링 중이면 중복 호출 방지
        asyncio.run_coroutine_threadsafe(self._hold(), self.loop)

    def is_hovering(self) -> bool:
        return self._is_hovering


def _is_stream_requested() -> bool:
    """command_receiver.py가 남긴 REQUEST_STREAM/STOP_STREAM 신호를 읽는다.
    파일이 없으면(아직 요청 없음) 기본값 False - 전송하지 않음."""
    try:
        import json as _json
        with open(STREAM_REQUEST_STATE_PATH, "r") as f:
            return bool(_json.load(f).get("stream_enabled", False))
    except Exception:
        return False


class MJPEGStreamServer:
    """
    RingBuffer와 별개로, 캡처 루프가 채우는 "최신 프레임 1장"만 계속
    JPEG로 인코딩해 MJPEG(multipart/x-mixed-replace)로 서빙하는 경량
    HTTP 서버. Tailscale 등으로 드론에 직접 붙어 실시간 확인하는
    테스트 전용 용도. main.py의 추론 파이프라인과는 완전히 독립적으로
    동작하며, 캡처 루프가 저장해두는 최신 프레임 변수만 읽어감(락 최소화).
    """

    def __init__(self, pipeline_ref, port: int, quality: int = STREAM_JPEG_QUALITY):
        self.pipeline_ref = pipeline_ref  # CameraAnomalyPipeline 인스턴스 참조
        self.port = port
        self.quality = quality
        self.httpd = None

    def start(self):
        quality = self.quality
        pipeline_ref = self.pipeline_ref

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass  # 기본 액세스 로그 억제 (콘솔 지저분해짐 방지)

            def do_GET(self):
                if self.path != "/stream":
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Use /stream")
                    return
                self.send_response(200)
                self.send_header("Age", "0")
                self.send_header("Cache-Control", "no-cache, private")
                self.send_header("Pragma", "no-cache")
                self.send_header(
                    "Content-Type",
                    "multipart/x-mixed-replace; boundary=FRAME",
                )
                self.end_headers()
                try:
                    last_check = 0.0
                    stream_allowed = False
                    while True:
                        # ★2026-08-21: 요청기반 스트리밍. 신호 파일을
                        # 1초에 한 번만 확인(매 프레임 파일 I/O 방지).
                        # command_receiver.py가 REQUEST_STREAM 받으면
                        # stream_enabled=true를 남기고, STOP_STREAM 받으면
                        # false로 되돌린다. 연결 자체(HTTP 접속)는 열려
                        # 있어도, 신호가 false면 실제 프레임 인코딩/전송을
                        # 건너뛰어 셀룰러 데이터가 발생하지 않게 한다.
                        now = time.time()
                        if now - last_check >= 1.0:
                            stream_allowed = _is_stream_requested()
                            last_check = now

                        if not stream_allowed:
                            time.sleep(0.5)
                            continue

                        frame = pipeline_ref.latest_frame_for_stream
                        if frame is None:
                            time.sleep(0.1)
                            continue
                        ok, jpg = cv2.imencode(
                            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality]
                        )
                        if not ok:
                            continue
                        data = jpg.tobytes()
                        self.wfile.write(b"--FRAME\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(data)}\r\n\r\n".encode())
                        self.wfile.write(data)
                        self.wfile.write(b"\r\n")
                        # 캡처 루프(FPS=9)를 그대로 따라감 - 별도 페이싱 불필요
                        time.sleep(1.0 / FPS)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # 클라이언트가 연결을 끊은 정상적인 상황

        self.httpd = ThreadingHTTPServer(("0.0.0.0", self.port), Handler)
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        logger.info(f"[Stream] MJPEG 스트리밍 서버 시작: http://<드론Tailscale IP>:{self.port}/stream")


class StreamUploader:
    """
    ★2026-08-21 서버 확정 스펙 구현: 요청기반 실시간 스트리밍의 실제
    프레임 전송 담당. STOMP가 아니라 HTTP(POST /drones/{droneId}/
    stream/frame)로 원본 JPEG 바이너리를 그대로 올린다 (base64 아님).

    command_receiver.py가 REQUEST_STREAM 수신 시 남기는 신호파일
    (STREAM_REQUEST_STATE_PATH)을 주기적으로 읽어 업로드 루프를
    켜고 끈다. main.py의 추론/캡처 루프와는 독립된 스레드로 동작.

    서버 스펙 핵심 규칙:
      - 응답 204: 계속 전송
      - 응답 410: 즉시 중지 (보는 사람 없음/세션 종료)
      - 응답 401: 디바이스 키 문제, 중지+로그
      - 10초 무응답: 스스로 중지 (STOP_STREAM만 믿으면 관제사가
        브라우저를 그냥 닫거나 서버가 재시작될 때 대응 못 함)
    """

    def __init__(self, drone_id: str, pipeline_ref):
        self.drone_id = drone_id
        self.pipeline_ref = pipeline_ref  # CameraAnomalyPipeline 인스턴스 참조
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("[StreamUpload] 업로드 감시 스레드 시작")

    def stop(self):
        self._running = False

    def _read_stream_state(self) -> Optional[dict]:
        try:
            import json as _json
            with open(STREAM_REQUEST_STATE_PATH, "r") as f:
                return _json.load(f)
        except Exception:
            return None

    def _loop(self):
        last_state_check = 0.0
        active = False
        state = None
        last_response_time = 0.0

        while self._running:
            now = time.time()

            # 신호파일은 1초에 한 번만 확인 (매 프레임 파일 I/O 방지)
            if now - last_state_check >= 1.0:
                state = self._read_stream_state()
                last_state_check = now
                new_active = bool(state and state.get("stream_enabled"))
                if new_active and not active:
                    logger.info(f"[StreamUpload] 전송 시작 (streamId={state.get('stream_id')})")
                    last_response_time = now  # 시작 시점부터 10초 카운트
                if not new_active and active:
                    logger.info("[StreamUpload] 전송 중지 (STOP_STREAM 또는 신호없음)")
                active = new_active

            if not active or state is None:
                time.sleep(0.5)
                continue

            # 10초 무응답 자체중지 (서버 확정 스펙 3-1)
            if now - last_response_time > STREAM_NO_RESPONSE_LIMIT_SEC:
                logger.warning(
                    f"[StreamUpload] {STREAM_NO_RESPONSE_LIMIT_SEC}초 무응답 - 스스로 중지"
                )
                active = False
                continue

            frame = self.pipeline_ref.latest_frame_for_stream
            if frame is None:
                time.sleep(0.1)
                continue

            width = state.get("width") or 640
            height = state.get("height") or 480
            quality = state.get("quality") or 70
            fps = state.get("fps") or 5
            stream_id = state.get("stream_id")
            upload_path = state.get("upload_path")

            if not upload_path or not stream_id:
                logger.warning("[StreamUpload] upload_path/stream_id 없음 - 전송 보류")
                time.sleep(0.5)
                continue

            try:
                resized = cv2.resize(frame, (width, height))
                ok, jpg = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, quality])
                if not ok:
                    time.sleep(1.0 / fps)
                    continue

                url = SERVER_HOST.rstrip("/") + upload_path
                headers = {
                    "Content-Type": "image/jpeg",
                    "X-Stream-Id": stream_id,
                }
                if DEVICE_KEY:
                    headers["X-Device-Key"] = DEVICE_KEY

                resp = requests.post(
                    url, headers=headers, data=jpg.tobytes(),
                    timeout=STREAM_FRAME_TIMEOUT_SEC,
                )

                if resp.status_code == 204:
                    last_response_time = time.time()
                elif resp.status_code == 410:
                    logger.info("[StreamUpload] 서버 410 Gone - 즉시 중지")
                    active = False
                elif resp.status_code == 401:
                    logger.error("[StreamUpload] 401 Unauthorized (디바이스 키 문제) - 중지")
                    active = False
                else:
                    logger.warning(f"[StreamUpload] 예상 밖 응답 {resp.status_code}")
                    last_response_time = time.time()  # 서버가 응답은 했으니 무응답 타이머는 리셋

            except requests.RequestException as e:
                logger.warning(f"[StreamUpload] 업로드 실패: {e}")
                # 네트워크 오류는 무응답 타이머를 리셋하지 않음 -> 10초 누적되면 자체중지

            time.sleep(1.0 / fps)


class CameraAnomalyPipeline:
    def __init__(self, hover_controller: DroneHoverController):
        self.buffer = RingBuffer(maxlen=BUFFER_MAXLEN)
        self.cap: Optional[cv2.VideoCapture] = None
        self._running = False
        self._last_trigger_time = 0.0
        self.hover = hover_controller
        self.latest_frame_for_stream = None  # MJPEGStreamServer가 읽어가는 최신 프레임

        if STREAM_ENABLED:
            self._stream_server = MJPEGStreamServer(self, STREAM_PORT)
            self._stream_server.start()
        else:
            self._stream_server = None

        # ★2026-08-21 서버확정: 실제 관제 스트리밍은 HTTP 업로드로 수행.
        # MJPEGStreamServer(위, Tailscale 직결 로컬용)와는 별개.
        drone_id = os.environ.get("DRONE_SYSID", "DR-01")
        self._stream_uploader = StreamUploader(drone_id, self)
        self._stream_uploader.start()

    def initialize_camera(self) -> None:
        pipeline = create_gstreamer_pipeline()
        self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not self.cap.isOpened():
            raise RuntimeError("CSI 카메라를 열 수 없습니다 (GStreamer 파이프라인 실패)")
        logger.info("CSI 카메라 초기화 완료")

    def release_camera(self) -> None:
        if self.cap is not None:
            self.cap.release()
            logger.info("CSI 카메라 해제 완료")

    def _check_trigger(self, score: float) -> bool:
        now = time.time()
        if score >= ANOMALY_THRESHOLD and (now - self._last_trigger_time) >= TRIGGER_COOLDOWN_SEC:
            self._last_trigger_time = now
            return True
        return False

    def run(self) -> None:
        self.initialize_camera()
        self._running = True
        frame_interval = 1.0 / FPS
        next_tick = time.time()

        logger.info(f"캡처 루프 시작 (FPS={FPS}, 버퍼={BUFFER_MAXLEN}프레임/{BUFFER_MAXLEN/FPS:.0f}초)")

        try:
            while self._running:
                ret, frame = self.cap.read()
                if not ret:
                    logger.warning("프레임 읽기 실패, 재시도")
                    time.sleep(0.1)
                    continue

                self.buffer.push(frame)
                self.latest_frame_for_stream = frame  # 스트리밍용 최신 프레임 갱신

                # 연속 추론: 버퍼가 충분히 찼으면 매 프레임 슬라이딩 윈도우로 추론
                if self.buffer.is_ready_for_inference():
                    window = self.buffer.get_latest_window(INFER_WINDOW_LEN)
                    score = detect_anomaly(window)

                    if self._check_trigger(score):
                        logger.info(f"⚠️ 이상 감지 트리거 발생 (score={score:.3f})")

                        # 1. 즉시 호버링
                        self.hover.hover_now()

                        # 2. 영상 전송 (동기 - 서버 응답 대기.
                        #    ★2026-07-18 공지: 응답에는 상태코드만 옴,
                        #    ttsAudioBase64 없음. 오디오는 STOMP로 별도 수신
                        #    (command_receiver.py의 PLAY_AUDIO 처리)
                        snapshot = self.buffer.get_full_buffer()
                        logger.info("영상 전송 중 (서버 응답 대기, 최대 180초)...")
                        result = upload_clip_sync(snapshot, anomaly_score=score)

                        if result:
                            logger.info(f"서버 응답 수신: {result}")
                        else:
                            logger.warning("서버 응답 없음/실패")

                        # 3. ★서버-드론팀 확정 사항: 재생/판정과 무관하게 자동 재개 안 함.
                        #    관제사가 STOMP로 PLAY_AUDIO(오디오) 또는
                        #    재개명령(START_PATROL/ROUTE_UPDATE)을 보낼 때까지
                        #    호버링 상태를 무한 유지함 (command_receiver.py가
                        #    별도 프로세스로 그 명령들을 수신해 처리).
                        logger.info("[Hover] 호버링 유지 중 - 관제사 명령 무한 대기 (command_receiver.py 경유)")

                # FPS 페이싱 (목표 9fps 유지)
                next_tick += frame_interval
                sleep_time = next_tick - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    next_tick = time.time()  # 밀린 경우 리셋

        finally:
            self.release_camera()

    def stop(self) -> None:
        self._running = False


def _signal_handler(pipeline: CameraAnomalyPipeline):
    def handler(signum, frame):
        logger.info(f"종료 시그널 수신 ({signum}), 정리 중...")
        pipeline.stop()
        sys.exit(0)
    return handler


if __name__ == "__main__":
    hover_controller = DroneHoverController()
    hover_controller.start()

    pipeline = CameraAnomalyPipeline(hover_controller)
    signal.signal(signal.SIGINT, _signal_handler(pipeline))
    signal.signal(signal.SIGTERM, _signal_handler(pipeline))
    pipeline.run()
