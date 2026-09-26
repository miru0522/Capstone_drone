"""운영 중인 main.py와 병행했을 때 보존 prototype의 자원 할당 비교용."""

from types import SimpleNamespace
import sys

import numpy as np

sys.path.insert(0, "/home/hpc/drone_2026/code")
from h264enctest import encode_frames_to_mp4_hw


frames = [
    SimpleNamespace(frame=np.zeros((540, 960, 3), dtype=np.uint8))
    for _ in range(3)
]
print(
    encode_frames_to_mp4_hw(
        frames,
        fps=9,
        bitrate=4_000_000,
        timeout_sec=15,
        out_path="/tmp/codex_h264_prototype_compare.mp4",
    )
)
