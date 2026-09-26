"""같은 81프레임으로 mp4v와 이벤트별 H264 subprocess 총시간을 비교한다."""

import os
import statistics
import sys
import time
from pathlib import Path

os.environ["H264_WORKER_PATH"] = str(Path(__file__).with_name("h264_encoder_worker.py"))
os.environ["H264_RAW_DIR"] = "/dev/shm"
os.environ["H264_STATE_PATH"] = "/tmp/codex_h264_benchmark_state.json"

import cv2

from ring_buffer import FrameEntry
import uploader


video_path = sys.argv[1]
cap = cv2.VideoCapture(video_path)
frames = []
while len(frames) < 81:
    ok, frame = cap.read()
    if not ok:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        continue
    frame = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA)
    frames.append(FrameEntry(frame=frame, timestamp=float(len(frames))))
cap.release()

measurements = {"mp4v": [], "h264": []}
for round_index in range(3):
    for name, function in (
        ("mp4v", uploader._encode_frames_mp4v),
        ("h264", uploader._encode_frames_h264),
    ):
        started = time.monotonic()
        output = function(frames, 9)
        elapsed = time.monotonic() - started
        size = os.path.getsize(output)
        os.remove(output)
        measurements[name].append(elapsed)
        print(
            f"round={round_index + 1} encoder={name} elapsed={elapsed:.3f}s "
            f"size={size}",
            flush=True,
        )

for name, values in measurements.items():
    print(
        f"summary encoder={name} values={values} median={statistics.median(values):.3f}s "
        f"max={max(values):.3f}s",
        flush=True,
    )
