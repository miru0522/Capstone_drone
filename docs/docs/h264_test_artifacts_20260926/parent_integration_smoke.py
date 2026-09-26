"""Jetson /tmp에서 uploader 부모부터 HW worker까지 연결하는 3프레임 검사."""

import json
import os
from pathlib import Path

os.environ["CLIP_ENCODER"] = "h264"
os.environ["H264_WORKER_PATH"] = str(Path(__file__).with_name("h264_encoder_worker.py"))
os.environ["H264_RAW_DIR"] = "/dev/shm"
os.environ["H264_STATE_PATH"] = "/tmp/codex_h264_parent_state.json"

import numpy as np

from ring_buffer import FrameEntry
from uploader import encode_frames_to_mp4


frames = [
    FrameEntry(frame=np.zeros((540, 960, 3), dtype=np.uint8), timestamp=float(i))
    for i in range(3)
]
output = encode_frames_to_mp4(frames, fps=9)
try:
    state = json.loads(Path(os.environ["H264_STATE_PATH"]).read_text(encoding="utf-8"))
    assert state["status"] == "ok", state
    assert state["total_successes"] >= 1, state
    print(f"PASS_PARENT_H264 path={output} size={os.path.getsize(output)} state={state}")
finally:
    try:
        os.remove(output)
    except FileNotFoundError:
        pass
