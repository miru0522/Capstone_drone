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
ANALYZE_URL = os.environ.get("ANALYZE_URL", "http://203.249.90.3:8000/analyze-video")
UPLOAD_TIMEOUT_SEC = 180          # 명세: AI 서버 무거우므로 넉넉히
UPLOAD_MODE = os.environ.get("UPLOAD_MODE", "A")   # "A" 또는 "B"
DRONE_ID = int(os.environ.get("DRONE_ID", "1"))    # B안에서 사용
MAX_RETRIES = 2
RETRY_BACKOFF_SEC = 2


def encode_frames_to_mp4(frames: List[FrameEntry], fps: int = FPS) -> str:
    """프레임 리스트 → mp4 임시파일 경로. 호출자가 삭제 책임."""
    if not frames:
        raise ValueError("encode_frames_to_mp4: 빈 프레임 리스트")

    h, w = frames[0].frame.shape[:2]
    fd, path = tempfile.mkstemp(suffix=".mp4", prefix="anomaly_clip_")
    os.close(fd)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
    try:
        for entry in frames:
            writer.write(entry.frame)
    finally:
        writer.release()

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
