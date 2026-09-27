"""운영 변경 없이 H264 조건을 무작위 교차 측정하는 1단계 연구 스크립트."""

import json
import os
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.environ["H264_WORKER_PATH"] = str(BASE_DIR / "research_h264_worker.py")
os.environ["H264_RAW_DIR"] = "/dev/shm"
os.environ["H264_STATE_PATH"] = "/tmp/codex_h264_stage1_state.json"
os.environ["H264_WORKER_LOG_PATH"] = "/tmp/codex_h264_stage1_worker.log"
os.environ["H264_WORKER_MODE"] = "persistent"

import cv2

from ring_buffer import FrameEntry
import uploader


SEED = 20260927
ROUNDS = 20
IDLE_SEC = 0.25


def percentile(values, percent):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percent / 100) * len(ordered) + 0.999999) - 1))
    return ordered[index]


def load_frames(video_path):
    cap = cv2.VideoCapture(video_path)
    frames = []
    while len(frames) < 81:
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        frame = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA)
        if not frame.flags.c_contiguous:
            frame = frame.copy()
        frames.append(FrameEntry(frame=frame, timestamp=float(len(frames))))
    cap.release()
    return frames


def write_raw_tobytes(frames, path):
    with open(path, "wb") as raw_file:
        for entry in frames:
            raw_file.write(entry.frame.tobytes(order="C"))


def write_raw_writev(frames, path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        views = [memoryview(entry.frame).cast("B") for entry in frames]
        while views:
            written = os.writev(fd, views)
            if written <= 0:
                raise OSError("os.writev가 데이터를 기록하지 못함")
            while views and written >= len(views[0]):
                written -= len(views[0])
                views.pop(0)
            if written and views:
                views[0] = views[0][written:]
    finally:
        os.close(fd)


def measure_mp4v(frames):
    started = time.monotonic()
    output = uploader._encode_frames_mp4v(frames, 9)
    elapsed = time.monotonic() - started
    size = os.path.getsize(output)
    os.remove(output)
    return {"total_sec": elapsed, "size_bytes": size}


def measure_h264(frames, bitrate, h264_job_index):
    started = time.monotonic()
    raw_fd, raw_path = tempfile.mkstemp(
        suffix=".bgr", prefix="h264_stage1_", dir=uploader.H264_RAW_DIR
    )
    os.close(raw_fd)
    final_path = None
    partial_path = None
    response_path = None
    try:
        raw_started = time.monotonic()
        write_raw_tobytes(frames, raw_path)
        raw_sec = time.monotonic() - raw_started

        out_fd, final_path = tempfile.mkstemp(suffix=".mp4", prefix="h264_stage1_")
        os.close(out_fd)
        os.remove(final_path)
        partial_path = final_path + ".partial"
        response_path = final_path + ".response.json"
        request = {
            "input_raw": raw_path,
            "output_partial": partial_path,
            "width": 960,
            "height": 540,
            "frames": len(frames),
            "fps": 9,
            "bitrate": bitrate,
        }

        wait_started = time.monotonic()
        process = uploader._run_persistent_worker(
            request, response_path, time.monotonic() + uploader.H264_TIMEOUT_SEC
        )
        worker_wait_sec = time.monotonic() - wait_started
        response = json.loads(Path(response_path).read_text(encoding="utf-8"))
        worker_encode_sec = float(response["worker_encode_sec"])

        finalize_started = time.monotonic()
        uploader._validate_h264_mp4(partial_path)
        os.replace(partial_path, final_path)
        partial_path = None
        finalize_sec = time.monotonic() - finalize_started
        size = os.path.getsize(final_path)
        total_sec = time.monotonic() - started
        return {
            "total_sec": total_sec,
            "raw_sec": raw_sec,
            "worker_wait_sec": worker_wait_sec,
            "worker_encode_sec": worker_encode_sec,
            "ipc_poll_fsync_sec": max(0.0, worker_wait_sec - worker_encode_sec),
            "finalize_sec": finalize_sec,
            "size_bytes": size,
            "worker_pid": process.pid,
            "h264_job_index": h264_job_index,
            "cold": h264_job_index == 1,
        }
    finally:
        for path in (raw_path, partial_path, final_path, response_path):
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass


def raw_profile(frames, output):
    rng = random.Random(SEED + 1)
    conditions = [name for _ in range(ROUNDS) for name in ("tobytes", "writev")]
    rng.shuffle(conditions)
    for sequence, name in enumerate(conditions, 1):
        fd, path = tempfile.mkstemp(suffix=".bgr", prefix="h264_raw_profile_", dir="/dev/shm")
        os.close(fd)
        started = time.monotonic()
        try:
            if name == "tobytes":
                write_raw_tobytes(frames, path)
            else:
                write_raw_writev(frames, path)
            elapsed = time.monotonic() - started
            record = {
                "kind": "raw_profile",
                "sequence": sequence,
                "condition": name,
                "elapsed_sec": elapsed,
            }
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        time.sleep(IDLE_SEC)


def main():
    video_path = sys.argv[1]
    result_path = Path(sys.argv[2])
    frames = load_frames(video_path)
    rng = random.Random(SEED)
    conditions = [name for _ in range(ROUNDS) for name in ("mp4v", "h264_4m", "h264_1m2")]
    rng.shuffle(conditions)
    h264_job_index = 0
    records = []

    with result_path.open("w", encoding="utf-8") as output:
        for sequence, condition in enumerate(conditions, 1):
            if condition == "mp4v":
                metrics = measure_mp4v(frames)
            else:
                h264_job_index += 1
                bitrate = 4_000_000 if condition == "h264_4m" else 1_200_000
                metrics = measure_h264(frames, bitrate, h264_job_index)
            record = {
                "kind": "encode",
                "sequence": sequence,
                "condition": condition,
                **metrics,
            }
            records.append(record)
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()
            print(json.dumps(record, ensure_ascii=False), flush=True)
            time.sleep(IDLE_SEC)

        raw_profile(frames, output)

    for condition in ("mp4v", "h264_4m", "h264_1m2"):
        values = [r["total_sec"] for r in records if r["condition"] == condition]
        warm_values = [
            r["total_sec"] for r in records
            if r["condition"] == condition and not r.get("cold", False)
        ]
        print(
            json.dumps(
                {
                    "summary": condition,
                    "count": len(values),
                    "p50_sec": statistics.median(values),
                    "p95_sec": percentile(values, 95),
                    "warm_p95_sec": percentile(warm_values, 95),
                    "max_sec": max(values),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    try:
        main()
    finally:
        uploader._stop_persistent_worker()
