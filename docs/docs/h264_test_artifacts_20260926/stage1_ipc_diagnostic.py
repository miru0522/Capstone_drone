"""지속 worker의 약 0.30초 잔차를 생산 단계별로 분해한다."""

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.environ["H264_WORKER_PATH"] = str(BASE_DIR / "research_h264_worker.py")
os.environ["H264_RAW_DIR"] = "/dev/shm"
os.environ["H264_STATE_PATH"] = "/tmp/codex_h264_ipc_state.json"
os.environ["H264_WORKER_LOG_PATH"] = "/tmp/codex_h264_ipc_worker.log"
os.environ["H264_WORKER_MODE"] = "persistent"

import cv2

from ring_buffer import FrameEntry
import uploader


ROUNDS = 20
IDLE_SEC = 0.25


def percentile(values, percent):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percent / 100) * len(ordered) + 0.999999) - 1))
    return ordered[index]


def load_frames(path):
    cap = cv2.VideoCapture(path)
    frames = []
    while len(frames) < 81:
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        frame = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA)
        frames.append(FrameEntry(frame=frame, timestamp=float(len(frames))))
    cap.release()
    return frames


def write_raw(frames, path):
    with open(path, "wb") as raw_file:
        for entry in frames:
            raw_file.write(entry.frame.tobytes(order="C"))


def run_job(frames, sequence):
    raw_fd, raw_path = tempfile.mkstemp(suffix=".bgr", prefix="h264_ipc_", dir="/dev/shm")
    os.close(raw_fd)
    out_fd, final_path = tempfile.mkstemp(suffix=".mp4", prefix="h264_ipc_")
    os.close(out_fd)
    os.remove(final_path)
    partial_path = final_path + ".partial"
    response_path = final_path + ".response.json"
    try:
        write_raw(frames, raw_path)
        request = {
            "input_raw": raw_path,
            "output_partial": partial_path,
            "width": 960,
            "height": 540,
            "frames": 81,
            "fps": 9,
            "bitrate": 1_200_000,
            "response_path": response_path,
        }

        with uploader._persistent_worker_lock:
            process = uploader._get_persistent_worker()
            state_started = time.monotonic()
            uploader._record_h264_state(
                "started", pid=process.pid, output_path=partial_path
            )
            state_ended = time.monotonic()

            serialize_started = time.monotonic()
            payload = json.dumps(request, ensure_ascii=False) + "\n"
            serialize_ended = time.monotonic()
            write_started = time.monotonic()
            process.stdin.write(payload)
            process.stdin.flush()
            write_ended = time.monotonic()

            while not os.path.exists(response_path):
                if process.poll() is not None:
                    raise RuntimeError(f"worker 종료: {process.returncode}")
                if time.monotonic() - write_ended > 15:
                    raise TimeoutError("IPC 진단 timeout")
                time.sleep(0.001)
            response_detected_at = time.monotonic()

        response = json.loads(Path(response_path).read_text(encoding="utf-8"))
        uploader._validate_h264_mp4(partial_path)
        return {
            "sequence": sequence,
            "state_sec": state_ended - state_started,
            "serialize_sec": serialize_ended - serialize_started,
            "stdin_write_flush_sec": write_ended - write_started,
            "stdin_to_worker_read_sec": max(
                0.0, response["worker_line_received_at"] - write_ended
            ),
            "worker_json_parse_sec": (
                response["worker_parsed_at"] - response["worker_line_received_at"]
            ),
            "worker_pre_encode_sec": (
                response["worker_encode_started_at"] - response["worker_parsed_at"]
            ),
            "worker_encode_sec": response["worker_encode_sec"],
            "response_fsync_replace_poll_sec": (
                response_detected_at - response["response_write_started_at"]
            ),
            "request_to_response_sec": response_detected_at - state_started,
        }
    finally:
        for path in (raw_path, partial_path, final_path, response_path):
            try:
                os.remove(path)
            except OSError:
                pass


def main():
    frames = load_frames(sys.argv[1])
    output_path = Path(sys.argv[2])
    rows = []
    with output_path.open("w", encoding="utf-8") as output:
        for sequence in range(1, ROUNDS + 1):
            row = run_job(frames, sequence)
            rows.append(row)
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            print(json.dumps(row, ensure_ascii=False), flush=True)
            time.sleep(IDLE_SEC)

    keys = [key for key in rows[0] if key != "sequence"]
    for key in keys:
        values = [row[key] for row in rows]
        print(
            json.dumps(
                {
                    "metric": key,
                    "p50_sec": statistics.median(values),
                    "p95_sec": percentile(values, 95),
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
