"""H264 persistent worker timeout 종료와 다음 요청 복구를 검증한다."""

import json
import os
import sys
import time
from pathlib import Path


CANDIDATE_DIR = Path("/tmp/h264_600_reapply_20260930/candidate")
OPERATION_DIR = Path("/home/hpc/drone_2026/code")
RESULT_PATH = Path("/tmp/h264_600_reapply_20260930/evidence/p0_timeout_recovery.json")
STATE_PATH = Path("/tmp/h264_600_reapply_timeout_state.json")

os.environ["CLIP_ENCODER"] = "h264"
os.environ["H264_BITRATE"] = "600000"
os.environ["H264_TIMEOUT_SEC"] = "15"
os.environ["H264_WORKER_PATH"] = str(CANDIDATE_DIR / "h264_encoder_worker.py")
os.environ["H264_RAW_DIR"] = "/dev/shm"
os.environ["H264_STATE_PATH"] = str(STATE_PATH)

sys.path.insert(0, str(CANDIDATE_DIR))
sys.path.insert(1, str(OPERATION_DIR))

import cv2

from ring_buffer import FrameEntry
from state_store import read_json
import uploader


def load_frames(video_path):
    capture = cv2.VideoCapture(video_path)
    frames = []
    while len(frames) < 81:
        ok, frame = capture.read()
        if not ok:
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        frame = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA)
        frames.append(FrameEntry(frame=frame, timestamp=len(frames) / 9.0))
    capture.release()
    return frames


def decode_count(path):
    capture = cv2.VideoCapture(path)
    count = 0
    while capture.isOpened():
        ok, _ = capture.read()
        if not ok:
            break
        count += 1
    capture.release()
    return count


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: p0_timeout_recovery.py VIDEO")
    try:
        STATE_PATH.unlink()
    except FileNotFoundError:
        pass
    frames = load_frames(sys.argv[1])
    result = {}
    output_path = None
    try:
        uploader.H264_TIMEOUT_SEC = 0.8
        started = time.monotonic()
        try:
            uploader._encode_frames_h264(frames, 9)
            raise RuntimeError("의도한 timeout이 발생하지 않음")
        except TimeoutError as exc:
            result["timeout"] = {
                "elapsed_sec": time.monotonic() - started,
                "error": str(exc),
                "worker_after": (
                    uploader._persistent_worker.pid
                    if uploader._persistent_worker is not None
                    else None
                ),
                "state": read_json(str(STATE_PATH), {}),
            }

        uploader.H264_TIMEOUT_SEC = 15.0
        started = time.monotonic()
        output_path = uploader._encode_frames_h264(frames, 9)
        worker = uploader._persistent_worker
        result["recovery"] = {
            "elapsed_sec": time.monotonic() - started,
            "worker_pid": worker.pid if worker is not None else None,
            "decoded_frames": decode_count(output_path),
            "size_bytes": os.path.getsize(output_path),
            "state": read_json(str(STATE_PATH), {}),
        }
        if result["timeout"]["worker_after"] is not None:
            raise RuntimeError("timeout 후 worker 참조가 정리되지 않음")
        if result["recovery"]["decoded_frames"] != 81:
            raise RuntimeError("복구 인코딩 프레임 수 불일치")
        result["status"] = "PASS"
        RESULT_PATH.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    finally:
        if output_path:
            uploader._remove_quietly(output_path)
        uploader._stop_persistent_worker()


if __name__ == "__main__":
    main()
