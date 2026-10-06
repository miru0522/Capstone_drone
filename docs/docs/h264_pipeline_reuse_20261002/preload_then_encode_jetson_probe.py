"""GStreamer 선로딩 후 기존 H264 encode 프로토콜의 호환성을 확인한다."""

import json
import os
import time

import numpy as np

from ring_buffer import FrameEntry


def main() -> None:
    import uploader

    started = time.monotonic()
    prepared = uploader.prepare_clip_encoder()
    prepare_sec = time.monotonic() - started
    process = uploader._persistent_worker
    if not prepared or process is None:
        raise RuntimeError("worker prepare 실패")

    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    frames = [
        FrameEntry(frame=frame, timestamp=0.0),
        FrameEntry(frame=frame, timestamp=1.0 / 9),
    ]
    started = time.monotonic()
    output_path = uploader.encode_frames_to_mp4(frames, fps=9)
    encode_sec = time.monotonic() - started
    try:
        result = {
            "prepared": prepared,
            "worker_pid": process.pid,
            "same_worker_after_encode": (
                uploader._persistent_worker is not None
                and uploader._persistent_worker.pid == process.pid
            ),
            "prepare_sec": prepare_sec,
            "first_encode_sec": encode_sec,
            "output_bytes": os.path.getsize(output_path),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["same_worker_after_encode"]:
            raise RuntimeError("prepare와 encode가 서로 다른 worker를 사용함")
    finally:
        uploader._remove_quietly(output_path)
        uploader._stop_persistent_worker()


if __name__ == "__main__":
    main()
