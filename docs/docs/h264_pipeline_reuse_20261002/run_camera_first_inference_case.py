"""W 또는 C 조건의 실카메라 probe를 정확히 1회 실행하고 증거를 수집한다."""

import argparse
import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path


ROOT = Path("/tmp/h264_preload_compare_20261006")
OPERATION_DIR = Path("/home/hpc/drone_2026/code")
PROBE = ROOT / "camera_first_inference_probe.py"
CANDIDATES = {
    "W": ROOT / "candidate_warmup",
    "C": ROOT / "candidate_preload_only",
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("condition", choices=("W", "C"))
    parser.add_argument("sequence", type=int)
    return parser.parse_args()


def process_snapshot():
    completed = subprocess.run(
        ["ps", "-eo", "pid,ppid,stat,etime,args"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    markers = ("main.py", "testermain.py", "camera_first_inference_probe.py")
    return [
        line.strip()
        for line in completed.stdout.splitlines()
        if any(marker in line for marker in markers)
    ]


def timestamp_tegrastats(process, output_path: Path):
    with output_path.open("w", encoding="utf-8") as output:
        for line in process.stdout:
            output.write(f"{time.time():.6f} {line}")
            output.flush()


def main() -> None:
    args = parse_args()
    condition = args.condition
    candidate = CANDIDATES[condition]
    evidence = ROOT / "evidence" / f"{args.sequence:02d}_{condition}"
    evidence.mkdir(parents=True, exist_ok=False)

    before = process_snapshot()
    occupied = [
        line
        for line in before
        if "python3 main.py" in line
        or "python3 testermain.py" in line
        or "camera_first_inference_probe.py" in line
    ]
    if occupied:
        raise RuntimeError(f"카메라 점유 가능 프로세스 존재: {occupied}")

    result_path = evidence / "probe_result.json"
    main_log_path = evidence / "probe.log"
    tegra_log_path = evidence / "tegrastats_timestamped.log"
    runner_path = evidence / "runner_result.json"

    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": f"{candidate}:{OPERATION_DIR}",
            "UPLOAD_MODE": "B",
            "CLIP_ENCODER": "h264",
            "H264_BITRATE": "600000",
            "H264_WORKER_MODE": "persistent",
            "H264_WORKER_PATH": str(candidate / "h264_encoder_worker.py"),
            "H264_RAW_DIR": "/dev/shm",
            "H264_STATE_PATH": str(evidence / "h264_state.json"),
            "H264_WORKER_LOG_PATH": str(evidence / "h264_worker.log"),
            "STREAM_ENABLED": "0",
            "STREAM_REQUEST_STATE_PATH": str(evidence / "stream_state.json"),
            "TEST_INJECT_STATE_PATH": str(evidence / "inject_state.json"),
            "ANOMALY_HOLD_STATE_PATH": str(evidence / "hover_state.json"),
            "PERIODIC_RECORD_STATE_PATH": str(evidence / "periodic_state.json"),
            "SERVER_URL": "http://127.0.0.1:9",
            "H264_PROBE_CONDITION": condition,
            "H264_PROBE_RESULT_PATH": str(result_path),
        }
    )

    started_at = time.time()
    tegra = subprocess.Popen(
        ["tegrastats", "--interval", "200"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    tegra_thread = threading.Thread(
        target=timestamp_tegrastats,
        args=(tegra, tegra_log_path),
        daemon=True,
    )
    tegra_thread.start()

    with main_log_path.open("w", encoding="utf-8") as main_log:
        process = subprocess.Popen(
            ["python3", str(PROBE)],
            cwd=str(OPERATION_DIR),
            env=env,
            stdout=main_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        timed_out = False
        sigterm_timed_out = False
        try:
            returncode = process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                returncode = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                sigterm_timed_out = True
                os.killpg(process.pid, signal.SIGKILL)
                returncode = process.wait(timeout=5)

    tegra.terminate()
    try:
        tegra.wait(timeout=5)
    except subprocess.TimeoutExpired:
        tegra.kill()
        tegra.wait(timeout=5)
    tegra_thread.join(timeout=2)

    probe_result = None
    if result_path.is_file():
        probe_result = json.loads(result_path.read_text(encoding="utf-8"))
    runner_result = {
        "condition": condition,
        "sequence": args.sequence,
        "started_at": started_at,
        "completed_at": time.time(),
        "elapsed_sec": time.time() - started_at,
        "probe_pid": process.pid,
        "returncode": returncode,
        "timed_out": timed_out,
        "sigterm_timed_out": sigterm_timed_out,
        "processes_before": before,
        "processes_after": process_snapshot(),
        "probe_status": probe_result.get("status") if probe_result else None,
        "probe_result_present": probe_result is not None,
    }
    runner_path.write_text(
        json.dumps(runner_result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(runner_result, ensure_ascii=False, indent=2), flush=True)
    if (
        timed_out
        or returncode != 0
        or not probe_result
        or probe_result.get("status") != "PASS"
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
