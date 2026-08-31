"""
uploader.py  (서버 명세 v최종 기준)
트리거 발생 시 RingBuffer 스냅샷 → mp4 인코딩 → AI 서버로 전송.

서버 명세 (drone_integration_spec.md 기준):
  URL   : http://203.249.90.3:8000/analyze-video
  방식  : HTTP POST, multipart/form-data
  타임아웃: 180초 (AI 서버가 무거움)

  A안 (현재): video 만 전송
  B안 (향후): video + drone_id(int) + anomaly_score(float)
             → Jigsaw 모델 탑재 후 사용

MODE 환경변수로 A/B 전환:
  UPLOAD_MODE = "A"  → 영상만
  UPLOAD_MODE = "B"  → 영상 + drone_id + anomaly_score
"""

import os
import time
import logging
import tempfile
import threading
from typing import List, Optional

import cv2
import requests

from ring_buffer import FrameEntry, FPS

logger = logging.getLogger("uploader")

# ─── 서버 명세 설정값 ────────────────────────────────────────────
ANALYZE_URL = os.environ.get("ANALYZE_URL", "http://203.249.90.3:8031/analyze-video")
UPLOAD_TIMEOUT_SEC = 180          # 명세: AI 서버 무거우므로 넉넉히
UPLOAD_MODE = os.environ.get("UPLOAD_MODE", "A")   # "A" 또는 "B"
DRONE_ID = os.environ.get("DRONE_ID", "DR-01")    # B안에서 사용 (telemetry_sender의 DRONE_SYSID와 통일)
MAX_RETRIES = 2
RETRY_BACKOFF_SEC = 2


def _h264_gstreamer_pipeline(path: str, w: int, h: int, fps: int) -> str:
    """Jetson 하드웨어 인코더(nvv4l2h264enc)를 사용하는 GStreamer 저장 파이프라인."""
    return (
        f"appsrc ! "
        f"video/x-raw,format=BGR,width={w},height={h},framerate={fps}/1 ! "
        f"videoconvert ! video/x-raw,format=NV12 ! "
        f"nvvidconv ! video/x-raw(memory:NVMM),format=NV12 ! "
        f"nvv4l2h264enc bitrate=4000000 ! "
        f"h264parse ! qtmux ! filesink location={path}"
    )


def encode_frames_to_mp4(frames: List[FrameEntry], fps: int = FPS) -> str:
    """
    프레임 리스트를 MP4 임시파일로 인코딩하고 경로를 반환.
    Jetson의 nvv4l2h264enc 경로는 VideoWriter가 열린 뒤
    write/release 단계에서 hang되는 현상이 확인되어 사용하지 않는다.
    검증된 OpenCV mp4v 인코더를 사용한다.
    호출자가 반환된 임시파일을 삭제할 책임이 있다.
    """
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
                    # B안: Jigsaw 점수 + 드론ID 함께 전송
                    data = {
                        "drone_id": str(DRONE_ID),
                        "anomaly_score": str(anomaly_score if anomaly_score is not None else 0.0),
                    }
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
                data = {
                    "drone_id": str(DRONE_ID),
                    "anomaly_score": str(anomaly_score if anomaly_score is not None else 0.0),
                }
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

