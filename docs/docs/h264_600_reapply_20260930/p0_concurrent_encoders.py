"""주기 녹화 4 Mbps와 이상 클립 600 kbps H264 동시 인코딩 P0 시험."""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


CANDIDATE_DIR = Path("/tmp/h264_600_reapply_20260930/candidate")
OPERATION_DIR = Path("/home/hpc/drone_2026/code")
PERIODIC_WORKER = OPERATION_DIR / "periodic_h264_encoder.py"
EVIDENCE_DIR = Path("/tmp/h264_600_reapply_20260930/evidence")
RESULT_PATH = EVIDENCE_DIR / "p0_concurrent_encoders.json"
TEGRASTATS_PATH = EVIDENCE_DIR / "p0_concurrent_tegrastats.log"
RAW_PATH = Path("/dev/shm/p0_periodic_4mbps_input.bgr")

os.environ["CLIP_ENCODER"] = "h264"
os.environ["H264_BITRATE"] = "600000"
os.environ["H264_WORKER_PATH"] = str(CANDIDATE_DIR / "h264_encoder_worker.py")
os.environ["H264_RAW_DIR"] = "/dev/shm"
os.environ["H264_STATE_PATH"] = "/tmp/h264_600_reapply_concurrent_state.json"

sys.path.insert(0, str(CANDIDATE_DIR))
sys.path.insert(1, str(OPERATION_DIR))

import cv2
import numpy as np

from ring_buffer import FrameEntry
import uploader


def load_frames(video_path):
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise RuntimeError(f"영상 열기 실패: {video_path}")
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


def write_raw(frames):
    with RAW_PATH.open("wb") as raw_file:
        for entry in frames:
            raw_file.write(np.ascontiguousarray(entry.frame).tobytes())


def decoded_frames(path):
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"결과 영상 열기 실패: {path}")
    count = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame is None or frame.size == 0:
            raise RuntimeError(f"빈 프레임: {path}, index={count}")
        count += 1
    capture.release()
    if count != 81:
        raise RuntimeError(f"프레임 수 불일치: {path}, {count}")
    return count


def resource_snapshot():
    meminfo = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in {"MemAvailable", "SwapFree"}:
            meminfo[key] = int(value.strip().split()[0])
    shm = shutil.disk_usage("/dev/shm")
    return {
        "mem_available_kib": meminfo.get("MemAvailable"),
        "swap_free_kib": meminfo.get("SwapFree"),
        "shm_free_bytes": shm.free,
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: p0_concurrent_encoders.py VIDEO")
    if not PERIODIC_WORKER.is_file():
        raise RuntimeError(f"주기 녹화 worker 없음: {PERIODIC_WORKER}")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    frames = load_frames(sys.argv[1])
    write_raw(frames)
    results = {
        "video": sys.argv[1],
        "rounds": [],
        "resource_before": resource_snapshot(),
    }

    tegra_file = TEGRASTATS_PATH.open("w", encoding="utf-8")
    tegra = subprocess.Popen(
        ["tegrastats", "--interval", "200"],
        stdout=tegra_file,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        for index in range(1, 11):
            periodic_output = Path(f"/tmp/p0_periodic_{index:02d}.mp4.partial")
            uploader_output = None
            command = [
                sys.executable,
                str(PERIODIC_WORKER),
                "--input-raw", str(RAW_PATH),
                "--output-partial", str(periodic_output),
                "--width", "960",
                "--height", "540",
                "--frames", "81",
                "--fps", "9",
                "--bitrate", "4000000",
            ]
            started = time.monotonic()
            periodic = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            h264_started = time.monotonic()
            try:
                uploader_output = uploader._encode_frames_h264(frames, 9)
                h264_elapsed = time.monotonic() - h264_started
                stdout, stderr = periodic.communicate(timeout=15)
                periodic_elapsed = time.monotonic() - started
                if periodic.returncode != 0:
                    raise RuntimeError(
                        f"주기 인코더 실패 rc={periodic.returncode}: {stderr.strip()}"
                    )
                worker = uploader._persistent_worker
                results["rounds"].append(
                    {
                        "round": index,
                        "h264_600_sec": h264_elapsed,
                        "periodic_4m_sec": periodic_elapsed,
                        "h264_600_size": os.path.getsize(uploader_output),
                        "periodic_4m_size": periodic_output.stat().st_size,
                        "h264_600_frames": decoded_frames(uploader_output),
                        "periodic_4m_frames": decoded_frames(periodic_output),
                        "persistent_worker_pid": (
                            worker.pid
                            if worker is not None and worker.poll() is None
                            else None
                        ),
                        "periodic_stdout": stdout.strip(),
                        "periodic_stderr": stderr.strip(),
                        "resource_after_round": resource_snapshot(),
                    }
                )
                print(json.dumps(results["rounds"][-1], ensure_ascii=False), flush=True)
            finally:
                if periodic.poll() is None:
                    periodic.terminate()
                    try:
                        periodic.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        periodic.kill()
                        periodic.wait(timeout=3)
                if uploader_output:
                    uploader._remove_quietly(uploader_output)
                uploader._remove_quietly(str(periodic_output))

        pids = {row["persistent_worker_pid"] for row in results["rounds"]}
        if len(pids) != 1 or None in pids:
            raise RuntimeError(f"persistent worker PID 재사용 실패: {pids}")
        results["resource_after"] = resource_snapshot()
        results["status"] = "PASS"
        RESULT_PATH.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    finally:
        tegra.terminate()
        try:
            tegra.wait(timeout=3)
        except subprocess.TimeoutExpired:
            tegra.kill()
            tegra.wait(timeout=3)
        tegra_file.close()
        uploader._stop_persistent_worker()
        uploader._remove_quietly(str(RAW_PATH))

    print(json.dumps({"status": results.get("status")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
