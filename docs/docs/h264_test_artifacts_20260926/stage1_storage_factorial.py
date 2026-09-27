"""운영 H264 함수 경계에서 상태/응답 저장소의 2x2 요인을 측정한다."""

import json
import multiprocessing
import os
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.environ["H264_WORKER_PATH"] = str(BASE_DIR / "research_h264_worker.py")
os.environ["H264_RAW_DIR"] = "/dev/shm"
os.environ["H264_STATE_PATH"] = "/tmp/codex_h264_factorial_import_state.json"
os.environ["H264_WORKER_LOG_PATH"] = "/tmp/codex_h264_factorial_worker.log"
os.environ["H264_WORKER_MODE"] = "persistent"
os.environ["H264_BITRATE"] = "1200000"

import cv2

from ring_buffer import FrameEntry
from state_store import read_json, update_json
import uploader


SEED = 20260927
ROUNDS = 20
IDLE_SEC = 0.25
MAIN_PID = 5563
MAIN_LOG = Path("/home/hpc/drone_2026/code/logs/main.log")
CONDITIONS = {
    "state_tmp_response_tmp": ("/tmp", "/tmp"),
    "state_shm_response_tmp": ("/dev/shm", "/tmp"),
    "state_tmp_response_shm": ("/tmp", "/dev/shm"),
    "state_shm_response_shm": ("/dev/shm", "/dev/shm"),
}

_response_dir = "/tmp"
_actual_response_path = None
_last_response_metrics = None
_original_run_persistent_worker = uploader._run_persistent_worker


def percentile(values, percent):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percent / 100) * len(ordered) + 0.999999) - 1))
    return ordered[index]


def load_frames(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"저장 영상 열기 실패: {video_path}")
    frames = []
    rewinds = 0
    while len(frames) < 81:
        ok, frame = cap.read()
        if not ok:
            rewinds += 1
            if rewinds > 100 or not cap.set(cv2.CAP_PROP_POS_FRAMES, 0):
                cap.release()
                raise RuntimeError(f"저장 영상에서 81프레임 준비 실패: {video_path}")
            ok, frame = cap.read()
            if not ok:
                cap.release()
                raise RuntimeError(f"저장 영상 rewind 후 프레임 읽기 실패: {video_path}")
        frame = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA)
        if not frame.flags.c_contiguous:
            frame = frame.copy()
        frames.append(FrameEntry(frame=frame, timestamp=float(len(frames))))
    cap.release()
    return frames


def routed_run_persistent_worker(request, original_response_path, deadline):
    """운영 함수는 유지하고 일회성 response 위치만 연구 조건으로 라우팅한다."""
    global _actual_response_path, _last_response_metrics
    name = Path(original_response_path).name
    _actual_response_path = str(Path(_response_dir) / name)
    _last_response_metrics = None
    try:
        process = _original_run_persistent_worker(request, _actual_response_path, deadline)
        _last_response_metrics = json.loads(
            Path(_actual_response_path).read_text(encoding="utf-8")
        )
        _last_response_metrics["parent_response_returned_at"] = time.monotonic()
        return process
    finally:
        try:
            os.remove(_actual_response_path)
        except OSError:
            pass


def lock_increment(path, count):
    for _ in range(count):
        update_json(
            path,
            lambda current: {"count": int((current or {}).get("count", 0)) + 1},
            default={"count": 0},
        )


def verify_shm_locking():
    path = "/dev/shm/codex_h264_factorial_lock_test.json"
    for suffix in ("", ".lock"):
        try:
            os.remove(path + suffix)
        except OSError:
            pass
    processes = [multiprocessing.Process(target=lock_increment, args=(path, 20)) for _ in range(2)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
    value = read_json(path, {}).get("count")
    lock_exists = os.path.exists(path + ".lock")
    ok = value == 40 and lock_exists and all(process.exitcode == 0 for process in processes)
    result = {"ok": ok, "count": value, "lock_exists": lock_exists}
    for suffix in ("", ".lock"):
        try:
            os.remove(path + suffix)
        except OSError:
            pass
    if not ok:
        raise RuntimeError(f"/dev/shm flock 사전검증 실패: {result}")
    return result


def read_memory_snapshot(reason, condition, sequence):
    values = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as meminfo:
        for line in meminfo:
            key, value = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                values[key + "_kib"] = int(value.strip().split()[0])
    shm = shutil.disk_usage("/dev/shm")
    return {
        "kind": "memory_snapshot",
        "reason": reason,
        "condition": condition,
        "sequence": sequence,
        **values,
        "shm_total_bytes": shm.total,
        "shm_free_bytes": shm.free,
        "main_pid_alive": Path(f"/proc/{MAIN_PID}").exists(),
        "captured_at": time.time(),
    }


def main_log_slice(start_offset, end_offset):
    if not MAIN_LOG.exists() or end_offset < start_offset:
        return ""
    with MAIN_LOG.open("rb") as log_file:
        log_file.seek(start_offset)
        return log_file.read(end_offset - start_offset).decode("utf-8", errors="replace")


def preflight_state_path(path):
    uploader.H264_STATE_PATH = path
    for suffix in ("", ".lock"):
        try:
            os.remove(path + suffix)
        except OSError:
            pass
    uploader._record_h264_state("started", pid=os.getpid(), output_path="preflight")
    if not os.path.exists(path) or Path(path).parent not in (Path("/tmp"), Path("/dev/shm")):
        raise RuntimeError(f"상태 경로 사전검증 실패: {path}")
    for suffix in ("", ".lock"):
        try:
            os.remove(path + suffix)
        except OSError:
            pass


def cleanup_test_state_files():
    paths = [
        "/tmp/codex_h264_factorial_import_state.json",
        "/tmp/codex_h264_factorial_preflight.json",
        "/dev/shm/codex_h264_factorial_preflight.json",
        "/tmp/codex_h264_factorial_state_tmp.json",
        "/dev/shm/codex_h264_factorial_state_shm.json",
    ]
    for path in paths:
        for suffix in ("", ".lock"):
            try:
                os.remove(path + suffix)
            except OSError:
                pass


def run_one(frames, condition, sequence):
    global _response_dir, _actual_response_path, _last_response_metrics
    state_dir, _response_dir = CONDITIONS[condition]
    state_path = str(Path(state_dir) / f"codex_h264_factorial_state_{Path(state_dir).name}.json")
    uploader.H264_STATE_PATH = state_path
    _actual_response_path = None
    _last_response_metrics = None
    log_start = MAIN_LOG.stat().st_size if MAIN_LOG.exists() else 0
    started = time.monotonic()
    output_path = uploader._encode_frames_h264(frames, 9)
    elapsed = time.monotonic() - started
    log_end = MAIN_LOG.stat().st_size if MAIN_LOG.exists() else log_start
    new_main_log = main_log_slice(log_start, log_end)
    state = read_json(state_path, {})
    response_path = _actual_response_path
    response = dict(_last_response_metrics or {})
    try:
        if state.get("status") != "ok":
            raise RuntimeError(f"succeeded 상태 기록 확인 실패: {state}")
        if not response_path or str(Path(response_path).parent) != _response_dir:
            raise RuntimeError(f"response 경로 확인 실패: {response_path}, expected={_response_dir}")
        return {
            "kind": "encode",
            "sequence": sequence,
            "condition": condition,
            "total_sec": elapsed,
            "size_bytes": os.path.getsize(output_path),
            "state_path": state_path,
            "state_dir_actual": str(Path(state_path).parent),
            "response_path": response_path,
            "response_dir_actual": str(Path(response_path).parent),
            "state_status": state.get("status"),
            "state_last_elapsed_sec": state.get("last_elapsed_sec"),
            "state_total_successes": state.get("total_successes"),
            "main_pid_alive": Path(f"/proc/{MAIN_PID}").exists(),
            "main_log_start_offset": log_start,
            "main_log_end_offset": log_end,
            "main_trigger_count": new_main_log.count("이상 감지 트리거 발생"),
            "main_mp4v_encode_count": new_main_log.count("mp4v 인코딩 완료"),
            "main_upload_start_count": new_main_log.count("영상 전송 시작"),
            "worker_encode_sec": response.get("worker_encode_sec"),
            "worker_pre_encode_sec": (
                response.get("worker_encode_started_at", 0.0)
                - response.get("worker_parsed_at", 0.0)
            ),
            "response_write_to_parent_return_sec": (
                response.get("parent_response_returned_at", 0.0)
                - response.get("response_write_started_at", 0.0)
            ),
        }
    finally:
        try:
            os.remove(output_path)
        except OSError:
            pass


def write_row(output, row):
    output.write(json.dumps(row, ensure_ascii=False) + "\n")
    output.flush()
    print(json.dumps(row, ensure_ascii=False), flush=True)


def main():
    frames = load_frames(sys.argv[1])
    result_path = Path(sys.argv[2])
    uploader._run_persistent_worker = routed_run_persistent_worker
    lock_result = verify_shm_locking()
    for state_dir in ("/tmp", "/dev/shm"):
        preflight_state_path(str(Path(state_dir) / "codex_h264_factorial_preflight.json"))

    conditions = [name for _ in range(ROUNDS) for name in CONDITIONS]
    random.Random(SEED).shuffle(conditions)
    rows = []
    previous = None
    with result_path.open("w", encoding="utf-8") as output:
        write_row(output, {"kind": "preflight", "shm_lock": lock_result, "seed": SEED})
        write_row(output, read_memory_snapshot("start", conditions[0], 0))
        for sequence, condition in enumerate(conditions, 1):
            if condition != previous:
                write_row(output, read_memory_snapshot("condition_transition", condition, sequence))
            row = run_one(frames, condition, sequence)
            rows.append(row)
            write_row(output, row)
            previous = condition
            time.sleep(IDLE_SEC)
        write_row(output, read_memory_snapshot("end", conditions[-1], len(conditions)))

    for condition in CONDITIONS:
        values = [row["total_sec"] for row in rows if row["condition"] == condition]
        print(json.dumps({
                "summary": condition,
                "count": len(values),
                "p50_sec": __import__("statistics").median(values),
                "p95_sec": percentile(values, 95),
                "max_sec": max(values),
            }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        uploader._run_persistent_worker = _original_run_persistent_worker
        uploader._stop_persistent_worker()
        cleanup_test_state_files()
