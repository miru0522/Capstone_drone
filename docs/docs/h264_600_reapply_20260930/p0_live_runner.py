"""P0-6 실제 CSI 카메라·VadCLIP·H264 시험을 격리 실행하고 원시 로그를 수집한다."""

import json
import os
import signal
import subprocess
import time
from pathlib import Path


ROOT = Path("/tmp/h264_600_reapply_20260930")
CANDIDATE = ROOT / "candidate"
EVIDENCE = ROOT / "evidence"
LIVE_MAIN = ROOT / "p0_live_main.py"
RESULT = EVIDENCE / "p0_live_camera_vadclip_h264.json"
RUNNER_RESULT = EVIDENCE / "p0_live_runner.json"
MAIN_LOG = EVIDENCE / "p0_live_main.log"
TEGRA_LOG = EVIDENCE / "p0_live_tegrastats.log"
OPERATION_DIR = Path("/home/hpc/drone_2026/code")


def process_snapshot():
    completed = subprocess.run(
        ["ps", "-eo", "pid,ppid,stat,etime,args"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    relevant = []
    for line in completed.stdout.splitlines():
        if any(
            marker in line
            for marker in (
                "main.py",
                "testermain.py",
                "h264_encoder_worker.py",
                "periodic_h264_encoder.py",
            )
        ):
            relevant.append(line.strip())
    return relevant


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    before = process_snapshot()
    if any("python3 main.py" in line or "python3 testermain.py" in line for line in before):
        raise RuntimeError(f"카메라 점유 가능 프로세스 존재: {before}")

    for path in (
        RESULT,
        Path("/tmp/h264_600_reapply_live_state.json"),
        Path("/tmp/h264_600_reapply_live_stream.json"),
        Path("/tmp/h264_600_reapply_live_inject.json"),
        Path("/tmp/h264_600_reapply_live_hover.json"),
        Path("/tmp/h264_600_reapply_live_periodic.json"),
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": f"{CANDIDATE}:{OPERATION_DIR}",
            "UPLOAD_MODE": "B",
            "CLIP_ENCODER": "h264",
            "H264_BITRATE": "600000",
            "H264_WORKER_PATH": str(CANDIDATE / "h264_encoder_worker.py"),
            "H264_RAW_DIR": "/dev/shm",
            "H264_STATE_PATH": "/tmp/h264_600_reapply_live_state.json",
            "STREAM_ENABLED": "0",
            "STREAM_REQUEST_STATE_PATH": "/tmp/h264_600_reapply_live_stream.json",
            "TEST_INJECT_STATE_PATH": "/tmp/h264_600_reapply_live_inject.json",
            "ANOMALY_HOLD_STATE_PATH": "/tmp/h264_600_reapply_live_hover.json",
            "PERIODIC_RECORD_STATE_PATH": "/tmp/h264_600_reapply_live_periodic.json",
            "SERVER_URL": "http://127.0.0.1:9",
            "P0_LIVE_RESULT_PATH": str(RESULT),
        }
    )

    started_at = time.time()
    with MAIN_LOG.open("w", encoding="utf-8") as main_log, TEGRA_LOG.open(
        "w", encoding="utf-8"
    ) as tegra_log:
        tegra = subprocess.Popen(
            ["tegrastats", "--interval", "200"],
            stdout=tegra_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        process = subprocess.Popen(
            ["python3", str(LIVE_MAIN)],
            cwd=str(OPERATION_DIR),
            env=env,
            stdout=main_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        timed_out = False
        try:
            returncode = process.wait(timeout=240)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                returncode = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                returncode = process.wait(timeout=5)
        finally:
            tegra.terminate()
            try:
                tegra.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tegra.kill()
                tegra.wait(timeout=5)

    live_result = None
    if RESULT.is_file():
        live_result = json.loads(RESULT.read_text(encoding="utf-8"))
    runner_result = {
        "started_at": started_at,
        "completed_at": time.time(),
        "elapsed_sec": time.time() - started_at,
        "main_pid": process.pid,
        "returncode": returncode,
        "timed_out": timed_out,
        "processes_before": before,
        "processes_after": process_snapshot(),
        "live_result_status": live_result.get("status") if live_result else None,
        "live_result_present": live_result is not None,
    }
    RUNNER_RESULT.write_text(
        json.dumps(runner_result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(runner_result, ensure_ascii=False, indent=2), flush=True)
    if timed_out or returncode != 0 or not live_result or live_result.get("status") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
