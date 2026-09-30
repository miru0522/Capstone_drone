"""서버 전송 없이 H264 600 후보의 mp4v/H264/폼 데이터 경로를 검증한다."""

import json
import os
import sys
import time
from pathlib import Path


CANDIDATE_DIR = Path("/tmp/h264_600_reapply_20260930/candidate")
OPERATION_DIR = Path("/home/hpc/drone_2026/code")
RESULT_PATH = Path("/tmp/h264_600_reapply_20260930/evidence/p0_parent_integration.json")

os.environ["CLIP_ENCODER"] = "h264"
os.environ["H264_BITRATE"] = "600000"
os.environ["UPLOAD_MODE"] = "B"
os.environ["H264_WORKER_PATH"] = str(CANDIDATE_DIR / "h264_encoder_worker.py")
os.environ["H264_RAW_DIR"] = "/dev/shm"
os.environ["H264_STATE_PATH"] = "/tmp/h264_600_reapply_20260930_h264_state.json"

sys.path.insert(0, str(CANDIDATE_DIR))
sys.path.insert(1, str(OPERATION_DIR))

import cv2

from ring_buffer import FrameEntry
import uploader


def load_frames(video_path: str):
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise RuntimeError(f"영상 열기 실패: {video_path}")
    frames = []
    while len(frames) < 81:
        ok, frame = capture.read()
        if not ok:
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        resized = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA)
        frames.append(FrameEntry(frame=resized, timestamp=float(len(frames)) / 9.0))
    capture.release()
    return frames


def validate_video(path: str):
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise RuntimeError(f"결과 영상 열기 실패: {path}")
    decoded = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame is None or frame.size == 0:
            raise RuntimeError(f"빈 프레임: {path}, index={decoded}")
        decoded += 1
    capture.release()
    if decoded != 81:
        raise RuntimeError(f"프레임 수 불일치: {decoded}")
    return decoded


def encode_once(name, function, frames):
    started = time.monotonic()
    output_path = function(frames, 9)
    elapsed = time.monotonic() - started
    try:
        worker = uploader._persistent_worker
        worker_pid = worker.pid if worker is not None and worker.poll() is None else None
        return {
            "name": name,
            "elapsed_sec": elapsed,
            "size_bytes": os.path.getsize(output_path),
            "decoded_frames": validate_video(output_path),
            "worker_pid": worker_pid,
        }
    finally:
        uploader._remove_quietly(output_path)


class MockResponse:
    status_code = 200

    @staticmethod
    def json():
        return {"mock": True}


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: p0_parent_integration.py VIDEO")

    frames = load_frames(sys.argv[1])
    results = {
        "video": sys.argv[1],
        "config": {
            "clip_encoder": uploader.CLIP_ENCODER,
            "h264_bitrate": uploader.H264_BITRATE,
            "upload_mode": uploader.UPLOAD_MODE,
            "worker_path": uploader.H264_WORKER_PATH,
        },
        "encodes": [],
        "mock_posts": [],
    }

    try:
        results["encodes"].append(
            encode_once("mp4v", uploader._encode_frames_mp4v, frames)
        )
        results["encodes"].append(
            encode_once("h264_cold", uploader._encode_frames_h264, frames)
        )
        results["encodes"].append(
            encode_once("h264_warm", uploader._encode_frames_h264, frames)
        )

        def mock_post(url, files, data=None, timeout=None):
            video_file = files["video"][1]
            results["mock_posts"].append(
                {
                    "url": url,
                    "data": dict(data or {}),
                    "timeout": timeout,
                    "video_size_bytes": os.fstat(video_file.fileno()).st_size,
                }
            )
            return MockResponse()

        uploader.requests.post = mock_post
        with_score = uploader.upload_clip_sync(frames, anomaly_score=0.654321)
        without_score = uploader.upload_clip_sync(frames, anomaly_score=None)
        results["mock_responses"] = [with_score, without_score]

        if results["encodes"][1]["worker_pid"] != results["encodes"][2]["worker_pid"]:
            raise RuntimeError("persistent worker PID가 재사용되지 않음")
        if results["mock_posts"][0]["data"].get("anomaly_score") != "0.654321":
            raise RuntimeError("유효 anomaly_score 폼 필드 오류")
        if "anomaly_score" in results["mock_posts"][1]["data"]:
            raise RuntimeError("None anomaly_score가 폼에 포함됨")
        if not all(row["data"].get("drone_id") for row in results["mock_posts"]):
            raise RuntimeError("drone_id 폼 필드 누락")

        results["status"] = "PASS"
        RESULT_PATH.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)
    finally:
        uploader._stop_persistent_worker()


if __name__ == "__main__":
    main()
