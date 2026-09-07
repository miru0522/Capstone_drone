#!/usr/bin/env python3
from pathlib import Path
import hashlib
import py_compile

CODE_DIR = Path("/home/hpc/drone_2026/code")
SRC = CODE_DIR / "90_edge_runtime_jetson_v4_trt.py"
DST = CODE_DIR / "122_edge_runtime_jetson_v5_async_upload.py"

EXPECTED_SRC_SHA256 = "6ed5857c7a4f085c9c26c8a0d3348e5028097a374baf720b6f39a320e7cbe037"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(
            f"{label}: expected exactly 1 match, found {n}. "
            "Refusing to patch an unexpected source."
        )
    return text.replace(old, new, 1)


if not SRC.exists():
    raise SystemExit(f"ERROR: source not found: {SRC}")

src_sha = sha256(SRC)
print("SOURCE =", SRC)
print("SOURCE_SHA256 =", src_sha)

if src_sha != EXPECTED_SRC_SHA256:
    raise SystemExit(
        "ERROR: v4 source hash does not match frozen baseline.\n"
        f"expected={EXPECTED_SRC_SHA256}\n"
        f"actual  ={src_sha}\n"
        "No file was modified."
    )

if DST.exists():
    raise SystemExit(
        f"ERROR: destination already exists: {DST}\n"
        "Refusing to overwrite."
    )

text = SRC.read_text(encoding="utf-8")

old = """        # VadCLIP 추론은 약 0.8초가 걸리므로 캡처 루프와 분리한다.
        # queue는 1개만 유지하며, 밀릴 경우 오래된 대기 window를 버리고 최신 window로 교체한다.
        self._inference_queue = queue.Queue(maxsize=1)
        self._inference_thread: Optional[threading.Thread] = None

        if STREAM_ENABLED:
"""

new = """        # VadCLIP 추론은 캡처 루프와 분리한다.
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
"""
text = replace_once(text, old, new, "add upload state")

old = """    def _handle_anomaly_score(self, score: float) -> None:
        if not self._check_trigger(score):
            return

        logger.info(f"⚠️ 이상 감지 트리거 발생 (score={score:.3f})")
        self.hover.hover_now()

        snapshot = self.buffer.get_full_buffer()
        logger.info("영상 전송 중 (서버 응답 대기, 최대 180초)...")
        result = upload_clip_sync(snapshot, anomaly_score=score)
        if result:
            logger.info(f"서버 응답 수신: {result}")
        else:
            logger.warning("서버 응답 없음/실패")
        logger.info("[Hover] 호버링 유지 중 - 관제사 명령 무한 대기 (command_receiver.py 경유)")

    def _inference_loop(self) -> None:
"""

new = """    def _handle_anomaly_score(self, score: float) -> None:
        if not self._check_trigger(score):
            return

        logger.info(f"⚠️ 이상 감지 트리거 발생 (score={score:.3f})")
        self.hover.hover_now()

        # get_full_buffer()는 FrameEntry들의 list snapshot을 반환한다.
        # deque가 이후 갱신돼도 이 list가 frame reference를 보유하므로 안전하다.
        snapshot = self.buffer.get_full_buffer()
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
"""
text = replace_once(text, old, new, "replace sync trigger upload")

old = """        self._running = True
        self._inference_thread = threading.Thread(target=self._inference_loop, daemon=True)
        self._inference_thread.start()
        frame_interval = 1.0 / FPS
"""

new = """        self._running = True

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
"""
text = replace_once(text, old, new, "start upload worker")

old = """    def stop(self) -> None:
        self._running = False
"""

new = """    def stop(self) -> None:
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
"""
text = replace_once(text, old, new, "improve stop")

text = replace_once(
    text,
    "# TRT V4 COPY — original main.py unchanged\n",
    "# TRT V5 ASYNC-UPLOAD COPY — original main.py and v4 unchanged\n",
    "header marker",
)

DST.write_text(text, encoding="utf-8")

try:
    py_compile.compile(str(DST), doraise=True)
except Exception:
    try:
        DST.unlink()
    except OSError:
        pass
    raise

dst_sha = sha256(DST)

print()
print("=" * 100)
print("V5 BUILD PASS")
print("=" * 100)
print("SOURCE_UNCHANGED_SHA256 =", sha256(SRC))
print("TARGET =", DST)
print("TARGET_SHA256 =", dst_sha)
print("COMPILE_RC = 0")
print("STATIC CHECKS:")

checks = [
    "self._upload_queue = queue.Queue(maxsize=1)",
    "self._upload_busy = threading.Event()",
    "def _submit_upload(",
    "def _upload_loop(",
    'name="clip-upload-worker"',
    'name="vadclip-inference-worker"',
    "upload_clip_sync(snapshot, anomaly_score=score)",
]
for s in checks:
    ok = s in text
    print(f"  {str(ok):5s}  {s}")
    if not ok:
        raise SystemExit("ERROR: static check failed after build")

print("STATUS=PASS")
