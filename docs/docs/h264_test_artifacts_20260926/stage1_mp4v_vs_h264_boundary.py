"""실제 mp4v와 선택된 H264 후보의 함수 반환 경계를 교차 측정한다."""

import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

import stage1_storage_factorial as common


SEED = 20260927
ROUNDS = 20
IDLE_SEC = 0.25
H264_CONDITION = "state_shm_response_shm"


def run_mp4v(frames, sequence):
    log_start = common.MAIN_LOG.stat().st_size if common.MAIN_LOG.exists() else 0
    started = time.monotonic()
    output_path = common.uploader._encode_frames_mp4v(frames, 9)
    elapsed = time.monotonic() - started
    log_end = common.MAIN_LOG.stat().st_size if common.MAIN_LOG.exists() else log_start
    new_main_log = common.main_log_slice(log_start, log_end)
    try:
        size = os.path.getsize(output_path)
        if size <= 0:
            raise RuntimeError(f"mp4v 결과 파일이 비어 있음: {output_path}")
        return {
            "kind": "encode",
            "sequence": sequence,
            "condition": "mp4v",
            "total_sec": elapsed,
            "size_bytes": size,
            "output_dir_actual": str(Path(output_path).parent),
            "main_pid_alive": Path(f"/proc/{common.MAIN_PID}").exists(),
            "main_log_start_offset": log_start,
            "main_log_end_offset": log_end,
            "main_trigger_count": new_main_log.count("이상 감지 트리거 발생"),
            "main_mp4v_encode_count": new_main_log.count("mp4v 인코딩 완료"),
            "main_upload_start_count": new_main_log.count("영상 전송 시작"),
        }
    finally:
        try:
            os.remove(output_path)
        except OSError:
            pass


def run_h264(frames, sequence):
    row = common.run_one(frames, H264_CONDITION, sequence)
    row["condition"] = "h264_shm_shm"
    return row


def main():
    frames = common.load_frames(sys.argv[1])
    result_path = Path(sys.argv[2])
    common.uploader._run_persistent_worker = common.routed_run_persistent_worker
    common._response_dir = "/dev/shm"
    lock_result = common.verify_shm_locking()
    common.preflight_state_path("/dev/shm/codex_h264_boundary_preflight.json")
    common.uploader.H264_STATE_PATH = "/dev/shm/codex_h264_factorial_state_shm.json"

    conditions = [name for _ in range(ROUNDS) for name in ("mp4v", "h264_shm_shm")]
    random.Random(SEED).shuffle(conditions)
    rows = []
    previous = None
    with result_path.open("w", encoding="utf-8") as output:
        common.write_row(output, {"kind": "preflight", "shm_lock": lock_result, "seed": SEED})
        common.write_row(output, common.read_memory_snapshot("start", conditions[0], 0))
        for sequence, condition in enumerate(conditions, 1):
            if condition != previous:
                common.write_row(
                    output,
                    common.read_memory_snapshot("condition_transition", condition, sequence),
                )
            row = (
                run_mp4v(frames, sequence)
                if condition == "mp4v"
                else run_h264(frames, sequence)
            )
            rows.append(row)
            common.write_row(output, row)
            previous = condition
            time.sleep(IDLE_SEC)
        common.write_row(output, common.read_memory_snapshot("end", conditions[-1], len(conditions)))

    for condition in ("mp4v", "h264_shm_shm"):
        values = [row["total_sec"] for row in rows if row["condition"] == condition]
        print(json.dumps({
            "summary": condition,
            "count": len(values),
            "p50_sec": statistics.median(values),
            "p95_sec": common.percentile(values, 95),
            "max_sec": max(values),
        }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        common.uploader._run_persistent_worker = common._original_run_persistent_worker
        common.uploader._stop_persistent_worker()
        common.cleanup_test_state_files()
        for path in (
            "/dev/shm/codex_h264_boundary_preflight.json",
            "/dev/shm/codex_h264_boundary_preflight.json.lock",
        ):
            try:
                os.remove(path)
            except OSError:
                pass
