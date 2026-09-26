"""
uploader.py  (서버 명세 v최종 기준)
트리거 발생 시 RingBuffer 스냅샷 → mp4 인코딩 → AI 서버로 전송.

서버 명세 (drone_integration_spec.md 기준):
  URL   : http://203.249.90.3:8031/analyze-video (nginx 리버스프록시 경유,
          8000/8080 직접 접속 불가)
  방식  : HTTP POST, multipart/form-data
  타임아웃: 180초 (AI 서버가 무거움)

  A안: video 만 전송 (구버전 호환)
  B안: video + drone_id + anomaly_score 전송 (현재 VadCLIP 운영 모드)

MODE 환경변수로 A/B 전환:
  UPLOAD_MODE = "A"  → 영상만
  UPLOAD_MODE = "B"  → 영상 + drone_id + anomaly_score
"""

import atexit
import json
import os
import signal
import shutil
import subprocess
import sys
import time
import logging
import tempfile
import threading
from pathlib import Path
from typing import List, Optional

import cv2
import requests

from ring_buffer import FrameEntry, FPS
from state_store import update_json

logger = logging.getLogger("uploader")

# ─── 서버 명세 설정값 ────────────────────────────────────────────
ANALYZE_URL = os.environ.get("ANALYZE_URL", "http://203.249.90.3:8031/analyze-video")
UPLOAD_TIMEOUT_SEC = 180          # 명세: AI 서버 무거우므로 넉넉히
UPLOAD_MODE = os.environ.get("UPLOAD_MODE", "A").upper()   # "A" 또는 "B"
DRONE_ID = os.environ.get("DRONE_ID", "DR-01")    # B안에서 사용 (telemetry_sender의 DRONE_SYSID와 통일)
MAX_RETRIES = 2
RETRY_BACKOFF_SEC = 2

# ─── 클립 인코더 설정 ────────────────────────────────────────────
# 운영 전환은 CLIP_ENCODER 한 값으로만 수행한다. H264 실패 시 같은 이벤트를
# mp4v로 다시 인코딩하지 않는다(지연 폭증과 중복 업로드 방지).
CLIP_ENCODER = os.environ.get("CLIP_ENCODER", "mp4v").strip().lower()
H264_BITRATE = int(os.environ.get("H264_BITRATE", "4000000"))
H264_TIMEOUT_SEC = float(os.environ.get("H264_TIMEOUT_SEC", "15"))
H264_WORKER_PATH = os.environ.get(
    "H264_WORKER_PATH",
    str(Path(__file__).with_name("h264_encoder_worker.py")),
)
H264_RAW_DIR = os.environ.get(
    "H264_RAW_DIR",
    "/dev/shm" if os.path.isdir("/dev/shm") else tempfile.gettempdir(),
)
H264_RAW_MIN_FREE_BYTES = int(
    os.environ.get("H264_RAW_MIN_FREE_BYTES", str(64 * 1024 * 1024))
)
H264_STATE_PATH = os.environ.get(
    "H264_STATE_PATH", "/tmp/drone_clip_encoder_state.json"
)
H264_WORKER_MODE = os.environ.get("H264_WORKER_MODE", "persistent").strip().lower()
H264_WORKER_LOG_PATH = os.environ.get(
    "H264_WORKER_LOG_PATH", "/tmp/drone_h264_worker.log"
)

if UPLOAD_MODE not in ("A", "B"):
    raise ValueError(f"UPLOAD_MODE는 A 또는 B여야 함: {UPLOAD_MODE}")
if CLIP_ENCODER not in ("mp4v", "h264"):
    raise ValueError(f"CLIP_ENCODER는 mp4v 또는 h264여야 함: {CLIP_ENCODER}")
if H264_BITRATE <= 0:
    raise ValueError(f"H264_BITRATE는 양수여야 함: {H264_BITRATE}")
if H264_TIMEOUT_SEC <= 0:
    raise ValueError(f"H264_TIMEOUT_SEC는 양수여야 함: {H264_TIMEOUT_SEC}")
if H264_RAW_MIN_FREE_BYTES < 0:
    raise ValueError(
        f"H264_RAW_MIN_FREE_BYTES는 0 이상이어야 함: {H264_RAW_MIN_FREE_BYTES}"
    )
if H264_WORKER_MODE not in ("per_event", "persistent"):
    raise ValueError(
        "H264_WORKER_MODE는 per_event 또는 persistent여야 함: "
        f"{H264_WORKER_MODE}"
    )


_persistent_worker = None
_persistent_worker_path = None
_persistent_worker_lock = threading.Lock()


def _build_form_data(anomaly_score: Optional[float]) -> dict:
    """B안 multipart 폼 데이터. 점수가 없으면 필드 자체를 보내지 않는다."""
    data = {"drone_id": str(DRONE_ID)}
    if anomaly_score is not None:
        data["anomaly_score"] = str(anomaly_score)
    return data


def _encode_frames_mp4v(frames: List[FrameEntry], fps: int) -> str:
    """기존 OpenCV mp4v 경로. CLIP_ENCODER=mp4v 롤백에 사용한다."""
    if not frames:
        raise ValueError("encode_frames_to_mp4: 빈 프레임 리스트")

    h, w = frames[0].frame.shape[:2]
    fd, path = tempfile.mkstemp(suffix=".mp4", prefix="anomaly_clip_")
    os.close(fd)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))

    if not writer.isOpened():
        try:
            os.remove(path)
        except OSError:
            pass
        raise RuntimeError("OpenCV mp4v VideoWriter 열기 실패")

    try:
        for entry in frames:
            writer.write(entry.frame)
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    finally:
        writer.release()

    if not os.path.exists(path) or os.path.getsize(path) <= 0:
        try:
            os.remove(path)
        except OSError:
            pass
        raise RuntimeError("MP4 인코딩 결과 파일이 비어 있음")

    logger.info(
        "mp4v 인코딩 완료: frames=%d, fps=%d, size=%d bytes",
        len(frames), fps, os.path.getsize(path)
    )

    return path


def _remove_quietly(path: Optional[str]) -> None:
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _terminate_process_group(process: subprocess.Popen) -> None:
    """멈춘 GStreamer 네이티브 호출을 부모 프로세스에서 격리 종료한다."""
    if process.poll() is not None:
        return

    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=2)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        logger.error("H264 인코더 프로세스 강제 종료 확인 실패: pid=%s", process.pid)


def _read_worker_log_tail() -> str:
    try:
        with open(H264_WORKER_LOG_PATH, "rb") as log_file:
            log_file.seek(0, os.SEEK_END)
            size = log_file.tell()
            log_file.seek(max(0, size - 2000))
            return log_file.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return "로그 없음"


def _stop_persistent_worker() -> None:
    global _persistent_worker, _persistent_worker_path
    process = _persistent_worker
    _persistent_worker = None
    _persistent_worker_path = None
    if process is not None and process.poll() is None:
        _terminate_process_group(process)


def _get_persistent_worker() -> subprocess.Popen:
    global _persistent_worker, _persistent_worker_path
    if (
        _persistent_worker is not None
        and _persistent_worker.poll() is None
        and _persistent_worker_path == H264_WORKER_PATH
    ):
        return _persistent_worker

    _stop_persistent_worker()
    log_directory = os.path.dirname(H264_WORKER_LOG_PATH) or "."
    os.makedirs(log_directory, exist_ok=True)
    log_file = open(H264_WORKER_LOG_PATH, "a", encoding="utf-8")
    popen_kwargs = {
        "stdin": subprocess.PIPE,
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
        "text": True,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    elif hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        process = subprocess.Popen(
            [sys.executable, H264_WORKER_PATH, "--serve"], **popen_kwargs
        )
    finally:
        log_file.close()

    _persistent_worker = process
    _persistent_worker_path = H264_WORKER_PATH
    logger.info(
        "h264_persistent_worker_started pid=%d log=%s",
        process.pid, H264_WORKER_LOG_PATH,
    )
    return process


atexit.register(_stop_persistent_worker)


def _validate_h264_mp4(path: str) -> None:
    """컨테이너 완결성과 H264 샘플 엔트리를 가볍게 확인한다."""
    if not os.path.exists(path) or os.path.getsize(path) <= 0:
        raise RuntimeError("H264 MP4 결과 파일이 비어 있음")

    with open(path, "rb") as f:
        data = f.read()
    if b"ftyp" not in data[:64] or b"moov" not in data:
        raise RuntimeError("H264 MP4 컨테이너가 완결되지 않음")
    if b"avc1" not in data and b"avc3" not in data:
        raise RuntimeError("MP4에서 H264 트랙을 확인할 수 없음")


def _check_raw_space(payload_bytes: int) -> None:
    """raw payload와 운영 안전 여유를 쓸 수 있는지 사전에 확인한다."""
    available = shutil.disk_usage(H264_RAW_DIR).free
    required = payload_bytes + H264_RAW_MIN_FREE_BYTES
    if available < required:
        raise RuntimeError(
            "H264 raw 저장공간 부족: "
            f"available={available}, required={required}, dir={H264_RAW_DIR}"
        )


def _record_h264_state(
    event: str,
    *,
    pid: Optional[int] = None,
    output_path: Optional[str] = None,
    error: Optional[str] = None,
    elapsed_sec: Optional[float] = None,
) -> None:
    """H264 작업기 시작/성공/실패와 연속 실패 횟수를 원자적으로 기록한다."""
    now = time.time()

    def apply(current):
        state = dict(current or {})
        state.setdefault("worker_starts", 0)
        state.setdefault("jobs_started", 0)
        state.setdefault("total_successes", 0)
        state.setdefault("total_failures", 0)
        state.setdefault("consecutive_failures", 0)

        if event == "started":
            state["jobs_started"] += 1
            if state.get("last_worker_pid") != pid:
                state["worker_starts"] += 1
                state["last_worker_pid"] = pid
            state["status"] = "encoding"
            state["active_pid"] = pid
            state["active_output_path"] = output_path
            state["last_started_at"] = now
        elif event == "succeeded":
            state["total_successes"] += 1
            state["consecutive_failures"] = 0
            state["status"] = "ok"
            state["active_pid"] = None
            state["active_output_path"] = None
            state["last_succeeded_at"] = now
            state["last_elapsed_sec"] = elapsed_sec
            state["last_error"] = None
        elif event == "failed":
            state["total_failures"] += 1
            state["consecutive_failures"] += 1
            state["status"] = (
                "rollback_recommended"
                if state["consecutive_failures"] >= 2
                else "error"
            )
            state["active_pid"] = None
            state["active_output_path"] = None
            state["last_failed_at"] = now
            state["last_elapsed_sec"] = elapsed_sec
            state["last_error"] = (error or "unknown")[-2000:]
        else:
            raise ValueError(f"알 수 없는 H264 상태 이벤트: {event}")
        return state

    try:
        state = update_json(H264_STATE_PATH, apply, default={})
        if event == "failed" and state and state["consecutive_failures"] >= 2:
            logger.error(
                "h264_rollback_recommended consecutive_failures=%d state_path=%s",
                state["consecutive_failures"], H264_STATE_PATH,
            )
    except Exception:
        logger.exception("H264 상태 파일 기록 실패: path=%s event=%s", H264_STATE_PATH, event)


def _run_per_event_worker(command, timeout_sec: float, output_path: str):
    popen_kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    elif hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    process = subprocess.Popen(command, **popen_kwargs)
    _record_h264_state("started", pid=process.pid, output_path=output_path)
    try:
        stdout, stderr = process.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process)
        try:
            stdout, stderr = process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        detail = (stderr or stdout or "출력 없음").strip()[-2000:]
        raise TimeoutError(
            f"H264 인코딩 제한시간 초과: {H264_TIMEOUT_SEC:.1f}초; "
            f"worker_output={detail}"
        ) from exc

    if process.returncode != 0:
        detail = (stderr or stdout or "출력 없음").strip()[-2000:]
        raise RuntimeError(
            f"H264 인코더 실패(returncode={process.returncode}): {detail}"
        )
    return process


def _run_persistent_worker(request: dict, response_path: str, deadline: float):
    with _persistent_worker_lock:
        process = _get_persistent_worker()
        _record_h264_state(
            "started", pid=process.pid, output_path=request["output_partial"]
        )
        request = dict(request)
        request["response_path"] = response_path
        try:
            process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            detail = _read_worker_log_tail()
            _stop_persistent_worker()
            raise RuntimeError(f"H264 지속 작업기 요청 실패: {detail}") from exc

        while True:
            if os.path.exists(response_path):
                with open(response_path, "r", encoding="utf-8") as response_file:
                    response = json.load(response_file)
                if response.get("ok"):
                    return process
                detail = str(response.get("error", "알 수 없는 작업기 오류"))[-2000:]
                _stop_persistent_worker()
                raise RuntimeError(f"H264 지속 작업기 실패: {detail}")

            returncode = process.poll()
            if returncode is not None:
                detail = _read_worker_log_tail()
                _stop_persistent_worker()
                raise RuntimeError(
                    f"H264 지속 작업기 종료(returncode={returncode}): {detail}"
                )
            if time.monotonic() >= deadline:
                detail = _read_worker_log_tail()
                _stop_persistent_worker()
                raise TimeoutError(
                    f"H264 인코딩 제한시간 초과: {H264_TIMEOUT_SEC:.1f}초; "
                    f"worker_output={detail}"
                )
            time.sleep(0.01)


def _encode_frames_h264(frames: List[FrameEntry], fps: int) -> str:
    """프레임을 raw BGR 파일로 넘겨 격리된 Jetson HW 인코더를 실행한다."""
    if not frames:
        raise ValueError("encode_frames_to_mp4: 빈 프레임 리스트")
    if fps <= 0:
        raise ValueError(f"fps는 양수여야 함: {fps}")

    first = frames[0].frame
    if first.ndim != 3 or first.shape[2] != 3:
        raise ValueError(f"BGR 3채널 프레임이 아님: shape={first.shape}")
    height, width = first.shape[:2]
    payload_bytes = width * height * 3 * len(frames)
    _check_raw_space(payload_bytes)

    raw_path = None
    partial_path = None
    final_path = None
    process = None
    response_path = None
    started = time.monotonic()

    try:
        raw_fd, raw_path = tempfile.mkstemp(
            suffix=".bgr", prefix="anomaly_clip_", dir=H264_RAW_DIR
        )
        with os.fdopen(raw_fd, "wb") as raw_file:
            for index, entry in enumerate(frames):
                frame = entry.frame
                if frame.shape != first.shape or frame.dtype.name != "uint8":
                    raise ValueError(
                        f"프레임 형식 불일치: index={index}, "
                        f"shape={frame.shape}, dtype={frame.dtype}"
                    )
                raw_file.write(frame.tobytes(order="C"))

        out_fd, final_path = tempfile.mkstemp(
            suffix=".mp4", prefix="anomaly_clip_h264_"
        )
        os.close(out_fd)
        os.remove(final_path)
        partial_path = final_path + ".partial"

        command = [
            sys.executable,
            H264_WORKER_PATH,
            "--input-raw", raw_path,
            "--output-partial", partial_path,
            "--width", str(width),
            "--height", str(height),
            "--frames", str(len(frames)),
            "--fps", str(fps),
            "--bitrate", str(H264_BITRATE),
        ]
        remaining = H264_TIMEOUT_SEC - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError(
                f"H264 raw 준비 중 제한시간 초과: {H264_TIMEOUT_SEC:.1f}초"
            )
        if H264_WORKER_MODE == "per_event":
            process = _run_per_event_worker(command, remaining, partial_path)
        else:
            response_path = final_path + ".response.json"
            request = {
                "input_raw": raw_path,
                "output_partial": partial_path,
                "width": width,
                "height": height,
                "frames": len(frames),
                "fps": fps,
                "bitrate": H264_BITRATE,
            }
            process = _run_persistent_worker(
                request, response_path, time.monotonic() + remaining
            )
        logger.info(
            "h264_job_completed pid=%d mode=%s output=%s frames=%d payload_bytes=%d",
            process.pid, H264_WORKER_MODE, partial_path, len(frames), payload_bytes,
        )

        _validate_h264_mp4(partial_path)
        os.replace(partial_path, final_path)
        partial_path = None

        elapsed = time.monotonic() - started
        logger.info(
            "h264(HW) 인코딩 완료: frames=%d, fps=%d, bitrate=%d, "
            "size=%d bytes, elapsed=%.3fs",
            len(frames), fps, H264_BITRATE, os.path.getsize(final_path), elapsed,
        )
        _record_h264_state("succeeded", elapsed_sec=elapsed)
        result = final_path
        final_path = None
        return result
    except Exception as exc:
        _record_h264_state(
            "failed",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_sec=time.monotonic() - started,
        )
        raise
    finally:
        if (
            H264_WORKER_MODE == "per_event"
            and process is not None
            and process.poll() is None
        ):
            _terminate_process_group(process)
        _remove_quietly(raw_path)
        _remove_quietly(partial_path)
        _remove_quietly(final_path)
        _remove_quietly(response_path)


def encode_frames_to_mp4(frames: List[FrameEntry], fps: int = FPS) -> str:
    """
    설정된 인코더로 MP4 임시파일을 만들고 경로를 반환한다.

    CLIP_ENCODER=mp4v: 기존 OpenCV 경로
    CLIP_ENCODER=h264: 별도 프로세스의 nvv4l2h264enc 경로
    호출자가 반환된 임시파일을 삭제할 책임이 있다.
    """
    if CLIP_ENCODER == "mp4v":
        return _encode_frames_mp4v(frames, fps)
    return _encode_frames_h264(frames, fps)


def _post_with_retry(path: str, anomaly_score: Optional[float]) -> bool:
    """
    명세 기준 전송 + 재시도.
    A안: files=video 만
    B안: files=video + data={drone_id, anomaly_score}
    """
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            with open(path, "rb") as f:
                files = {"video": (os.path.basename(path), f, "video/mp4")}

                if UPLOAD_MODE.upper() == "B":
                    # B안: anomaly_score + 드론ID 함께 전송
                    data = _build_form_data(anomaly_score)
                    resp = requests.post(ANALYZE_URL, files=files, data=data,
                                         timeout=UPLOAD_TIMEOUT_SEC)
                else:
                    # A안: 영상만
                    resp = requests.post(ANALYZE_URL, files=files,
                                         timeout=UPLOAD_TIMEOUT_SEC)

            if resp.status_code == 200:
                logger.info(f"[{UPLOAD_MODE}안] 업로드 성공: {path} -> {ANALYZE_URL}")
                logger.info(f"서버 응답: {resp.text[:200]}")
                return True
            logger.warning(f"업로드 실패 (status={resp.status_code}), 시도 {attempt}")
        except requests.RequestException as e:
            logger.warning(f"업로드 오류 (시도 {attempt}): {e}")

        if attempt <= MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SEC * attempt)

    logger.error(f"업로드 최종 실패: {path}")
    return False


def upload_clip_async(
    frames: List[FrameEntry],
    anomaly_score: Optional[float] = None,
    trigger_timestamp: Optional[float] = None,  # 호환용(현재 서버 미사용)
) -> threading.Thread:
    """프레임 리스트를 백그라운드 스레드에서 인코딩 + 전송."""

    def _worker():
        path = None
        try:
            path = encode_frames_to_mp4(frames)
            _post_with_retry(path, anomaly_score)
        except Exception as e:
            logger.exception(f"업로드 워커 예외: {e}")
        finally:
            if path is not None:
                try:
                    os.remove(path)
                except Exception:
                    pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t

def upload_clip_sync(
    frames: List[FrameEntry],
    anomaly_score: Optional[float] = None,
) -> Optional[dict]:
    """
    프레임 리스트를 동기적으로 인코딩+전송하고, 서버 응답 JSON을 반환.
    호버링 후 서버의 판정(ttsAudioBase64 등)을 즉시 받아야 하는
    이상감지 트리거 경로에서 사용. (기존 upload_clip_async는 fire-and-forget
    용도로 그대로 유지, 이 함수는 응답이 필요한 경우 전용)

    Returns:
        서버 응답 JSON dict, 실패 시 None
    """
    path = None
    try:
        path = encode_frames_to_mp4(frames, fps=FPS)
        with open(path, "rb") as f:
            files = {"video": (os.path.basename(path), f, "video/mp4")}

            if UPLOAD_MODE.upper() == "B":
                data = _build_form_data(anomaly_score)
                resp = requests.post(ANALYZE_URL, files=files, data=data,
                                     timeout=UPLOAD_TIMEOUT_SEC)
            else:
                resp = requests.post(ANALYZE_URL, files=files,
                                     timeout=UPLOAD_TIMEOUT_SEC)

        if resp.status_code == 200:
            logger.info(f"[동기전송] 성공: {path} -> {ANALYZE_URL}")
            try:
                return resp.json()
            except ValueError:
                logger.error("서버 응답이 JSON이 아님")
                return None
        else:
            logger.warning(f"[동기전송] 실패 (status={resp.status_code})")
            return None

    except requests.RequestException as e:
        logger.error(f"[동기전송] 요청 오류: {e}")
        return None
    except Exception as e:
        logger.exception(f"[동기전송] 예외: {e}")
        return None
    finally:
        if path is not None:
            try:
                os.remove(path)
            except Exception:
                pass
