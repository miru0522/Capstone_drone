"""Jetson 격리 환경에서 GStreamer 선로딩이 NVENC를 열지 않는지 확인한다."""

import glob
import json
import os
from pathlib import Path


def main() -> None:
    import uploader

    raw_dir = Path(uploader.H264_RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    state_path = Path(uploader.H264_STATE_PATH)
    state_before = state_path.read_bytes() if state_path.exists() else None

    ok = uploader.prepare_clip_encoder()
    process = uploader._persistent_worker
    if not ok or process is None or process.poll() is not None:
        raise RuntimeError("prepare 후 persistent worker가 살아 있지 않음")

    pid = process.pid
    maps = Path(f"/proc/{pid}/maps").read_text(encoding="utf-8", errors="replace")
    fd_targets = []
    for fd_path in glob.glob(f"/proc/{pid}/fd/*"):
        try:
            fd_targets.append(os.readlink(fd_path))
        except OSError:
            pass

    state_after = state_path.read_bytes() if state_path.exists() else None
    leftovers = sorted(
        str(path)
        for path in raw_dir.iterdir()
        if path.name.startswith(("h264_prepare_", "anomaly_clip_"))
    )
    result = {
        "ok": ok,
        "worker_pid": pid,
        "worker_alive": process.poll() is None,
        "gstreamer_mapped": "libgstreamer-1.0" in maps,
        "nvenc_device_fds": [
            target
            for target in fd_targets
            if "msenc" in target.lower() or "nvenc" in target.lower()
        ],
        "state_existed_before": state_before is not None,
        "state_existed_after": state_after is not None,
        "state_unchanged": state_before == state_after,
        "temporary_leftovers": leftovers,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    uploader._stop_persistent_worker()

    if not result["gstreamer_mapped"]:
        raise RuntimeError("worker maps에서 libgstreamer-1.0을 찾지 못함")
    if result["nvenc_device_fds"]:
        raise RuntimeError("prepare 단계에서 NVENC 장치를 열었음")
    if not result["state_unchanged"]:
        raise RuntimeError("prepare 단계가 운영 상태 파일을 변경함")
    if result["temporary_leftovers"]:
        raise RuntimeError("prepare 단계 임시 파일이 남음")


if __name__ == "__main__":
    main()
