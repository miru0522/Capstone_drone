# TRT V6 MEMORY-SAFE ASYNC-UPLOAD COPY — original main.py/v4/v5 unchanged
"""
main.py
CSI 카메라(GStreamer) -> RingBuffer -> 추론 -> 트리거 -> 영상전송 + 호버링

트리거(이상 감지) 시 동작:
  1. MAVSDK action.hold() 로 즉시 호버링 (제자리 정지)
  2. 영상을 서버(/analyze-video)로 전송
  3. 호버링 상태 유지 (재개는 command_receiver.py가 STOMP로 받는
     별도 명령으로 처리 예정 - 아직 서버와 재개 명령 형식 미정)

Edge 이상탐지는 VadCLIP으로 동작한다. 기존 Jigsaw-VAD/WideBranchNet은
Git 기준본으로 롤백 가능하며, downstream 트리거/전송/호버링 인터페이스는 유지한다.
"""

import os
import time
import logging
import signal
import sys
import asyncio
import threading
import queue
from typing import Optional
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
import requests
from mavsdk import System

from ring_buffer import RingBuffer, FrameEntry, FPS, BUFFER_MAXLEN, INFER_WINDOW_LEN
from uploader import upload_clip_async, upload_clip_sync
from anomaly_model_trt import AnomalyPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main_v4_trt")

# V6: live CSI / VadCLIP input resolution is unchanged.
# Only the anomaly clip queued to the upload worker is reduced.
UPLOAD_CLIP_WIDTH = int(os.environ.get("UPLOAD_CLIP_WIDTH", "960"))
UPLOAD_CLIP_HEIGHT = int(os.environ.get("UPLOAD_CLIP_HEIGHT", "540"))


# ─── 카메라 설정 ──────────────────────────────────────────────────
# ★2026-09-03: IMX219 mode2(1920x1080, 30fps 상한)로 화질 상향 시도.
# 8MP(mode0, 3280x2464)는 메모리부족(NvMapMemHandleAlloc)으로 실기 전체가
# 응답불가 상태까지 갔던 전력이 있어 그보다 한 단계 낮은 해상도로 검증 중.
# 문제 시 sensor-mode=4, 1280x720(CAMERA_WIDTH/HEIGHT=1280/720)로 롤백.
CAMERA_WIDTH = 1920
CAMERA_HEIGHT = 1080
# VadCLIP UCF-Crime 기준의 임시 통합 임계값. 드론 도메인 calibration 전까지
# 운영 최종값으로 간주하지 않으며 환경변수로 즉시 교체할 수 있다.
ANOMALY_THRESHOLD = float(os.environ.get("ANOMALY_THRESHOLD", "0.4073"))
TRIGGER_COOLDOWN_SEC = 9    # 같은 클립을 중복 전송하지 않도록 쿨다운

# VadCLIP 한 판정은 10 snippet을 feature buffer에 추가한다. 9fps 라이브에서
# 약 5.33초(48프레임) 창을 모두 소비한 뒤 다음 판정을 수행해, 겹치는 창에서
# 동일 시간대 feature가 중복 push되는 것을 막는다.
INFERENCE_INTERVAL_FRAMES = INFER_WINDOW_LEN

# ─── 실시간 스트리밍 설정 (테스트/Tailscale 직결 전용) ─────────────
STREAM_ENABLED = os.environ.get("STREAM_ENABLED", "1") == "1"
STREAM_PORT = int(os.environ.get("STREAM_PORT", "8090"))
STREAM_JPEG_QUALITY = 80  # 0~100, 높을수록 고화질/고용량

# ★2026-08-21: 요청기반 스트리밍. command_receiver.py(별도 프로세스)가
# REQUEST_STREAM/STOP_STREAM 수신 시 이 파일에 신호를 남긴다.
STREAM_REQUEST_STATE_PATH = os.environ.get("STREAM_REQUEST_STATE_PATH", "/tmp/drone_stream_request.json")

# 데모/리허설 전용: 카메라 대신 지정된 영상을 일정 시간 캡처 루프에 주입한다.
# 운영 중 신호파일이 없으면 TestVideoInjector는 완전히 비활성(오버헤드 없음).
TEST_INJECT_STATE_PATH = os.environ.get("TEST_INJECT_STATE_PATH", "/tmp/drone_test_inject.json")

# ★2026-08-21 서버 확정 스펙: 영상은 STOMP가 아니라 HTTP로 전송.
# (STOMP에 영상을 얹으면 EMERGENCY_STOP 등 제어명령이 영상 프레임
#  뒤에 큐잉되어 늦게 도착하는 안전문제가 있다는 서버팀 설명 반영)
SERVER_HOST = os.environ.get("SERVER_URL", "http://203.249.90.3:8031")
DEVICE_KEY = os.environ.get("DEVICE_KEY", "HPC-2026")
STREAM_FRAME_TIMEOUT_SEC = 5.0     # 프레임 1장 업로드 타임아웃
STREAM_NO_RESPONSE_LIMIT_SEC = 10.0  # 이 시간 무응답이면 자체 중지 (서버 확정 스펙)
MAVSDK_URI = "serial:///dev/pixhawk:115200"


def create_gstreamer_pipeline(width=CAMERA_WIDTH, height=CAMERA_HEIGHT, fps=FPS) -> str:
    """CSI 카메라용 GStreamer 파이프라인 문자열 생성."""
    return (
        f"nvarguscamerasrc sensor_id=0 sensor-mode=2 ! "
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


INFERENCE_FAILURE_ALERT_THRESHOLD = 10  # 이만큼 연속 실패하면 경고 강화

_consecutive_inference_failures = 0


def detect_anomaly(window: np.ndarray) -> float:
    """
    VadCLIP 실제 추론.
    window: (T,H,W,C) BGR uint8, T=INFER_WINDOW_LEN(기본 48, 약 5.33초 @ 9fps)
    반환: anomaly_score 0.0~1.0 (높을수록 이상)
    """
    global _consecutive_inference_failures
    try:
        pipeline = get_anomaly_pipeline()
        score = pipeline.compute_score(window)
        if _consecutive_inference_failures > 0:
            logger.info(f"✅ 모델 추론 복구됨 ({_consecutive_inference_failures}회 연속 실패 후)")
        _consecutive_inference_failures = 0
        return score
    except Exception as e:
        # ★2026-08-26: 추론 실패는 여전히 0.0(정상)으로 처리해 오탐/불필요한
        # 호버링을 막지만(기존 fail-safe 유지), 엔진이 완전히 죽은 채로
        # 계속 조용히 0.0만 반환하면 운영자가 전혀 알 수 없었음. 연속 실패
        # 횟수를 세어 임계치 이상이면 눈에 띄게(critical) 경고한다.
        _consecutive_inference_failures += 1
        if _consecutive_inference_failures >= INFERENCE_FAILURE_ALERT_THRESHOLD:
            logger.critical(
                f"🚨 모델 추론 {_consecutive_inference_failures}회 연속 실패 - "
                f"엔진/GPU 상태 확인 필요 (이상감지가 사실상 멈춰있을 수 있음): {e}"
            )
        else:
            logger.error(f"모델 추론 실패 ({_consecutive_inference_failures}회 연속): {e}")
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

    def _disable_stream_state(self, reason: str) -> None:
        """서버가 중지를 지시했을 때 신호파일의 stream_enabled 도 내린다.

        메모리 변수(active)만 내리면 _loop 가 1초 뒤 신호파일을 다시 읽어
        stream_enabled=true 를 보고 전송을 되살린다. 그 플래그는 STOP_STREAM
        을 받을 때만 꺼지므로, 410/401 로 멈춰도 1초 뒤 재시작되어 무한히
        반복된다. 되살아날 때마다 last_response_time 도 초기화되므로
        10초 무응답 자체중지 안전망까지 무력해진다.
        """
        try:
            import json as _json
            state = self._read_stream_state() or {}
            state["stream_enabled"] = False
            state["disabled_reason"] = reason
            with open(STREAM_REQUEST_STATE_PATH, "w") as f:
                _json.dump(state, f)
            logger.info(f"[StreamUpload] 신호파일 stream_enabled=false 기록 ({reason})")
        except Exception as e:
            logger.warning(f"[StreamUpload] 신호파일 중지 기록 실패: {e}")

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
                self._disable_stream_state("no_response")
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
                    self._disable_stream_state("410")
                elif resp.status_code == 401:
                    logger.error("[StreamUpload] 401 Unauthorized (디바이스 키 문제) - 중지")
                    active = False
                    self._disable_stream_state("401")
                else:
                    logger.warning(f"[StreamUpload] 예상 밖 응답 {resp.status_code}")
                    last_response_time = time.time()  # 서버가 응답은 했으니 무응답 타이머는 리셋

            except requests.RequestException as e:
                logger.warning(f"[StreamUpload] 업로드 실패: {e}")
                # 네트워크 오류는 무응답 타이머를 리셋하지 않음 -> 10초 누적되면 자체중지

            time.sleep(1.0 / fps)


class TestVideoInjector:
    """
    데모/리허설 전용: 실행 중인 main.py의 캡처 루프에서, 실제 카메라 프레임 대신
    지정된 영상 파일의 프레임을 일정 시간(duration_sec) 동안 대신 공급한다.

    StreamUploader의 신호파일 패턴과 동일하게, 1초에 한 번만 신호파일
    (TEST_INJECT_STATE_PATH)을 확인한다. 신호파일이 없으면(평상시/운영 중)
    이 클래스는 아무 것도 하지 않아 오버헤드가 없다.

    신호파일 형식: {"video_path": "...", "duration_sec": 15, "requested_at": <epoch>}
    같은 requested_at은 한 번만 소비한다(중복 주입 방지).

    ⚠️ 데모/리허설 전용이며 운영 트리거 로직(threshold, cooldown, hover 등)은
    전혀 건드리지 않는다 - 주입된 프레임도 실제 카메라 프레임과 동일하게
    RingBuffer -> VadCLIP 추론 -> 트리거 -> 업로드 경로를 그대로 통과한다.
    """

    def __init__(self):
        self._cap: Optional[cv2.VideoCapture] = None
        self._end_time: float = 0.0
        self._consumed_at: Optional[float] = None
        self._last_check: float = 0.0

    def _check_new_request(self, now: float) -> None:
        if now - self._last_check < 1.0:
            return
        self._last_check = now
        try:
            import json as _json
            with open(TEST_INJECT_STATE_PATH, "r") as f:
                req = _json.load(f)
        except Exception:
            return

        requested_at = req.get("requested_at")
        if requested_at is None or requested_at == self._consumed_at:
            return

        video_path = req.get("video_path")
        duration = float(req.get("duration_sec", 15))
        if not video_path or not os.path.exists(video_path):
            logger.warning(f"[TestInject] 영상 경로 없음/찾을 수 없음: {video_path}")
            self._consumed_at = requested_at
            return

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning(f"[TestInject] 영상 열기 실패: {video_path}")
            self._consumed_at = requested_at
            return

        if self._cap is not None:
            self._cap.release()
        self._cap = cap
        self._end_time = now + duration
        self._consumed_at = requested_at
        logger.warning(
            f"[TestInject] \u26a0\ufe0f 테스트 모드 진입: {duration:.0f}초간 카메라 대신 "
            f"'{video_path}' 프레임을 주입합니다 (실제 카메라 입력 아님)"
        )

    def maybe_get_frame(self):
        """활성 상태면 (True, frame)을, 아니면 (False, None)을 반환한다."""
        now = time.time()
        self._check_new_request(now)

        if self._cap is None:
            return False, None

        if now >= self._end_time:
            logger.warning("[TestInject] 테스트 모드 종료 - 실제 카메라로 복귀")
            self._cap.release()
            self._cap = None
            return False, None

        ret, frame = self._cap.read()
        if not ret:
            # 영상이 끝나면 처음부터 반복 재생 (duration 다 찰 때까지)
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self._cap.read()
            if not ret:
                logger.warning("[TestInject] 영상 재생 실패 - 실제 카메라로 복귀")
                self._cap.release()
                self._cap = None
                return False, None
        return True, frame


class CameraAnomalyPipeline:
    def __init__(self, hover_controller: DroneHoverController):
        self.buffer = RingBuffer(maxlen=BUFFER_MAXLEN)
        self._test_injector = TestVideoInjector()  # 데모/리허설 전용
        self.cap: Optional[cv2.VideoCapture] = None
        self._running = False
        self._last_trigger_time = 0.0
        self.hover = hover_controller
        self.latest_frame_for_stream = None  # MJPEGStreamServer가 읽어가는 최신 프레임

        # VadCLIP 추론은 캡처 루프와 분리한다.
        # queue는 1개만 유지하며, 밀릴 경우 오래된 대기 window를 버리고 최신 window로 교체한다.
        self._inference_queue = queue.Queue(maxsize=1)
        self._inference_thread: Optional[threading.Thread] = None

        # V5: 이상 clip 인코딩 + /analyze-video 업로드를 VadCLIP inference worker와 분리.
        # 서버 응답은 최대 180초까지 걸릴 수 있으므로 inference worker에서 sync upload를
        # 직접 수행하면 그 시간 동안 새 VadCLIP 판정이 정지한다.
        # outstanding upload는 최대 1개만 허용해 Xavier NX backlog를 막는다.
        self._upload_queue = queue.Queue(maxsize=1)
        self._upload_thread: Optional[threading.Thread] = None
        self._upload_busy = threading.Event()

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
        # Jetson Xavier NX는 VadCLIP/PyTorch가 먼저 대규모 메모리를 점유하면
        # Argus/NVMM CaptureSession 생성에 필요한 연속 메모리 확보가 실패할 수 있다.
        # 따라서 모델 로드 전에 카메라 세션을 먼저 만들고 실제 첫 프레임까지 확인한다.
        if self.cap is not None and self.cap.isOpened():
            return

        pipeline = create_gstreamer_pipeline()
        self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not self.cap.isOpened():
            self.release_camera()
            raise RuntimeError("CSI 카메라를 열 수 없습니다 (GStreamer 파이프라인 실패)")

        ret, _frame = self.cap.read()
        if not ret:
            self.release_camera()
            raise RuntimeError("CSI 카메라 CaptureSession은 열렸지만 첫 프레임 획득에 실패했습니다")

        logger.info("CSI 카메라 초기화 및 첫 프레임 확인 완료")

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

    def _make_upload_snapshot(self):
        full = self.buffer.get_full_buffer()
        if not full:
            return []

        t0 = time.time()
        reduced = []
        full.reverse()
        while full:
            entry = full.pop()
            frame_small = cv2.resize(
                entry.frame,
                (UPLOAD_CLIP_WIDTH, UPLOAD_CLIP_HEIGHT),
                interpolation=cv2.INTER_AREA,
            )
            reduced.append(
                FrameEntry(frame=frame_small, timestamp=entry.timestamp)
            )

        elapsed_ms = (time.time() - t0) * 1000.0
        logger.info(
            "V6 upload snapshot 준비: frames=%d, resolution=%dx%d, elapsed=%.1fms",
            len(reduced), UPLOAD_CLIP_WIDTH, UPLOAD_CLIP_HEIGHT, elapsed_ms
        )
        return reduced

    def _handle_anomaly_score(self, score: float) -> None:
        if not self._check_trigger(score):
            return

        logger.info(f"⚠️ 이상 감지 트리거 발생 (score={score:.3f})")
        self.hover.hover_now()

        # V6: long-lived upload job에는 reduced snapshot만 보낸다.
        # live ring과 VadCLIP 입력 해상도는 그대로 유지된다.
        snapshot = self._make_upload_snapshot()
        submitted = self._submit_upload(snapshot, score)

        if submitted:
            logger.info(
                "영상 전송 job 제출 완료 "
                f"(frames={len(snapshot)}); VadCLIP inference worker는 계속 동작"
            )
        else:
            logger.warning(
                "이미 clip 업로드가 진행 중이므로 중복 전송 생략; "
                "VadCLIP inference는 계속 동작"
            )

        logger.info("[Hover] 호버링 유지 중 - 관제사 명령 무한 대기 (command_receiver.py 경유)")

    def _submit_upload(self, snapshot, score: float) -> bool:
        if self._upload_busy.is_set():
            return False

        self._upload_busy.set()
        try:
            self._upload_queue.put_nowait((snapshot, score))
            return True
        except queue.Full:
            self._upload_busy.clear()
            return False

    def _upload_loop(self) -> None:
        logger.info("clip upload worker 시작")
        while self._running:
            try:
                snapshot, score = self._upload_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                logger.info(
                    "영상 전송 시작 "
                    f"(frames={len(snapshot)}, score={score:.3f}, 서버 응답 최대 180초)"
                )
                result = upload_clip_sync(snapshot, anomaly_score=score)
                if result:
                    logger.info(f"서버 응답 수신: {result}")
                else:
                    logger.warning("서버 응답 없음/실패")
            except Exception:
                logger.exception("clip upload worker 예외")
            finally:
                self._upload_busy.clear()
                self._upload_queue.task_done()

    def _inference_loop(self) -> None:
        logger.info("VadCLIP 추론 worker 시작")
        while self._running:
            try:
                window = self._inference_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                score = detect_anomaly(window)
                self._handle_anomaly_score(score)
            except Exception:
                logger.exception("VadCLIP inference worker 예외")
            finally:
                self._inference_queue.task_done()

    def _submit_inference(self, window: np.ndarray) -> None:
        # 정상 상태에서는 추론(~0.8s) << 주기(5.33s)라 queue가 비어 있어야 한다.
        # 서버 업로드 등으로 worker가 오래 막히면 오래된 대기 window 대신 최신 window만 보존한다.
        try:
            self._inference_queue.put_nowait(window)
            return
        except queue.Full:
            pass

        try:
            _ = self._inference_queue.get_nowait()
            self._inference_queue.task_done()
            logger.warning("VadCLIP worker 지연: 대기 중인 오래된 window를 최신 window로 교체")
        except queue.Empty:
            pass
        try:
            self._inference_queue.put_nowait(window)
        except queue.Full:
            logger.warning("VadCLIP worker queue 갱신 실패 - 이번 window 스킵")

    def run(self) -> None:
        # __main__에서 VadCLIP보다 먼저 카메라를 선점한 경우 재오픈하지 않는다.
        if self.cap is None or not self.cap.isOpened():
            self.initialize_camera()
        self._running = True

        self._upload_thread = threading.Thread(
            target=self._upload_loop,
            name="clip-upload-worker",
            daemon=True,
        )
        self._upload_thread.start()

        self._inference_thread = threading.Thread(
            target=self._inference_loop,
            name="vadclip-inference-worker",
            daemon=True,
        )
        self._inference_thread.start()

        frame_interval = 1.0 / FPS
        next_tick = time.time()

        # ★2026-08-26 진단용: 캡처 루프가 목표 FPS를 못 따라가는지(=추론이
        # 프레임 간격보다 오래 걸려 밀리는지) 확인. 1초 단위로 실제 처리
        # 프레임 수와 밀린 시간 누적을 요약 로그.
        diag_frame_count = 0
        diag_lag_total = 0.0
        diag_window_start = time.time()

        inference_counter = 0  # INFERENCE_INTERVAL_FRAMES마다만 추론 실행

        logger.info(
            f"캡처 루프 시작 (FPS={FPS}, 버퍼={BUFFER_MAXLEN}프레임/{BUFFER_MAXLEN/FPS:.0f}초, "
            f"추론주기={INFERENCE_INTERVAL_FRAMES}프레임/{INFERENCE_INTERVAL_FRAMES/FPS:.2f}초)"
        )

        try:
            while self._running:
                injected, frame = self._test_injector.maybe_get_frame()
                if not injected:
                    ret, frame = self.cap.read()
                    if not ret:
                        logger.warning("프레임 읽기 실패, 재시도")
                        time.sleep(0.1)
                        continue

                self.buffer.push(frame)
                self.latest_frame_for_stream = frame  # 스트리밍용 최신 프레임 갱신

                # VadCLIP: INFERENCE_INTERVAL_FRAMES(기본 48프레임 ≈ 5.33초)마다
                # 한 번씩 비중첩 시간 창을 추론한다. 각 호출은 새 10 snippet을
                # VadCLIP rolling feature buffer에 추가한다.
                inference_counter += 1
                if self.buffer.is_ready_for_inference() and inference_counter >= INFERENCE_INTERVAL_FRAMES:
                    inference_counter = 0
                    window = self.buffer.get_latest_window(INFER_WINDOW_LEN)
                    self._submit_inference(window)

                # FPS 페이싱 (목표 9fps 유지)
                next_tick += frame_interval
                sleep_time = next_tick - time.time()

                # ★2026-08-26 진단용 계측
                diag_frame_count += 1
                if sleep_time < 0:
                    diag_lag_total += -sleep_time
                now_diag = time.time()
                if now_diag - diag_window_start >= 1.0:
                    logger.info(
                        f"[진단] 최근 {now_diag - diag_window_start:.1f}초간 "
                        f"처리프레임={diag_frame_count}(목표 {FPS}), "
                        f"밀린시간누적={diag_lag_total * 1000:.0f}ms"
                    )
                    diag_frame_count = 0
                    diag_lag_total = 0.0
                    diag_window_start = now_diag

                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    next_tick = time.time()  # 밀린 경우 리셋

        finally:
            self.release_camera()

    def stop(self) -> None:
        self._running = False
        try:
            self._stream_uploader.stop()
        except Exception:
            logger.exception("StreamUploader stop 중 예외")

        if self._upload_busy.is_set():
            logger.warning(
                "종료 시 clip upload가 아직 진행 중입니다. "
                "upload worker는 daemon이므로 프로세스 종료와 함께 중단될 수 있습니다."
            )


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

    # 중요: Xavier NX 통합 메모리에서는 VadCLIP/PyTorch를 먼저 로드하면
    # Argus CaptureSession용 NVMM 연속 메모리 확보가 실패할 수 있다.
    # 카메라 세션과 첫 프레임을 먼저 확보한 뒤 모델을 로드/warmup한다.
    # warmup 후 실제 추론은 별도 worker에서 실행되어 9fps 캡처를 막지 않는다.
    try:
        pipeline.initialize_camera()
        get_anomaly_pipeline().warmup()
        pipeline.run()
    except Exception:
        pipeline.release_camera()
        raise
