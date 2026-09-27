"""두 장면에서 mp4v/H264 persistent worker 장시간 안정성을 교차 측정한다."""

import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

import cv2

import stage1_storage_factorial as common


SEED = int(os.environ.get("STAGE2_SEED", "20260927"))
ROUNDS = int(os.environ.get("STAGE2_ROUNDS", "100"))
IDLE_SEC = float(os.environ.get("STAGE2_IDLE_SEC", "3.0"))
MAIN_PID = int(os.environ["STAGE2_MAIN_PID"])
H264_CONDITION = "state_shm_response_shm"


def process_metrics(pid):
    status_path = Path(f"/proc/{pid}/status")
    if not status_path.exists():
        return None
    values = {}
    for line in status_path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(":")
        if key in {"VmRSS", "Threads"}:
            values[key] = int(value.strip().split()[0])
    try:
        fd_count = len(list(Path(f"/proc/{pid}/fd").iterdir()))
    except OSError:
        fd_count = None
    return {
        "pid": pid,
        "rss_kib": values.get("VmRSS"),
        "threads": values.get("Threads"),
        "fd_count": fd_count,
    }


def validate_decode(path, expected_frames):
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise RuntimeError(f"출력 영상 열기 실패: {path}")
    decoded = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame is None or frame.size == 0:
            capture.release()
            raise RuntimeError(f"빈 디코딩 프레임: {path}, index={decoded}")
        decoded += 1
    capture.release()
    if decoded != expected_frames:
        raise RuntimeError(
            f"디코딩 프레임 수 불일치: path={path}, decoded={decoded}, "
            f"expected={expected_frames}"
        )
    return decoded


def base_result(video_name, condition, sequence, started, output_path, frames):
    elapsed = time.monotonic() - started
    decoded = validate_decode(output_path, len(frames))
    worker = common.uploader._persistent_worker
    worker_pid = worker.pid if worker is not None and worker.poll() is None else None
    return {
        "kind": "encode",
        "video": video_name,
        "condition": condition,
        "sequence": sequence,
        "total_sec": elapsed,
        "size_bytes": os.path.getsize(output_path),
        "decoded_frames": decoded,
        "uploader": process_metrics(os.getpid()),
        "worker": process_metrics(worker_pid) if worker_pid else None,
        "main_pid_alive": Path(f"/proc/{MAIN_PID}").exists(),
        "captured_at": time.time(),
    }


def run_mp4v(video_name, frames, sequence):
    started = time.monotonic()
    output_path = common.uploader._encode_frames_mp4v(frames, 9)
    try:
        return base_result(
            video_name, "mp4v", sequence, started, output_path, frames
        )
    finally:
        common.uploader._remove_quietly(output_path)


def run_h264(video_name, frames, sequence):
    common._response_dir = "/dev/shm"
    common._actual_response_path = None
    common._last_response_metrics = None
    state_path = "/dev/shm/codex_h264_stage2_state.json"
    common.uploader.H264_STATE_PATH = state_path
    started = time.monotonic()
    output_path = common.uploader._encode_frames_h264(frames, 9)
    try:
        row = base_result(
            video_name, "h264_shm_shm", sequence, started, output_path, frames
        )
        state = common.read_json(state_path, {})
        response = dict(common._last_response_metrics or {})
        response_path = common._actual_response_path
        if state.get("status") != "ok":
            raise RuntimeError(f"H264 상태 기록 실패: {state}")
        if not response_path or Path(response_path).parent != Path("/dev/shm"):
            raise RuntimeError(f"H264 response 경로 오류: {response_path}")
        # 2026-09-27 수정: 승인된 후보 worker(h264_encoder_worker.py)의 응답은
        # {"ok": True/False, "error": ...}뿐이라 worker_encode_sec/
        # response_write_started_at 같은 타이밍 필드가 존재하지 않는다. 이전 코드는
        # 이 필드들을 stage1_storage_factorial.py가 대상으로 삼던 연구용
        # research_h264_worker.py의 응답 스키마 기준으로 읽어와 .get() 기본값(0.0)을
        # 실제 time.monotonic() 값(≈시스템 uptime)에서 빼는 무의미한 값을 만들었다.
        # 지금 승인된 후보로는 이 하위 지표를 측정할 수 없으므로 제거하고, 같은
        # 프로세스 내에서 유효하게 측정되는 total_sec로 p50/p95 통과 기준을 판정한다.
        row.update(
            {
                "state_status": state.get("status"),
                "state_total_successes": state.get("total_successes"),
                "response_path": response_path,
            }
        )
        return row
    finally:
        common.uploader._remove_quietly(output_path)


def summary(rows, started):
    result = {
        "kind": "summary",
        "elapsed_sec": time.monotonic() - started,
        "rounds_per_video_condition": ROUNDS,
        "idle_sec": IDLE_SEC,
        "conditions": {},
        "worker_pids": sorted(
            {
                row["worker"]["pid"]
                for row in rows
                if row.get("worker") is not None
            }
        ),
        "orphan_paths": sorted(
            str(path)
            for pattern in ("anomaly_clip_*.bgr", "*.response.json", "*.lock")
            for path in Path("/dev/shm").glob(pattern)
            if "codex_h264_stage2_state" not in path.name
        ),
    }
    for video_name in sorted({row["video"] for row in rows}):
        for condition in ("mp4v", "h264_shm_shm"):
            selected = [
                row
                for row in rows
                if row["video"] == video_name and row["condition"] == condition
            ]
            values = [row["total_sec"] for row in selected]
            result["conditions"][f"{video_name}:{condition}"] = {
                "count": len(selected),
                "p50_sec": statistics.median(values),
                "p95_sec": common.percentile(values, 95),
                "max_sec": max(values),
                "decoded_all": all(row["decoded_frames"] == 81 for row in selected),
            }
    return result


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: stage2_stability.py VIDEO_A VIDEO_B RESULT_JSONL")
    common.MAIN_PID = MAIN_PID
    # MUST 수정(2026-09-27, Claude 검수): stage1_storage_factorial import 시점에
    # H264_WORKER_PATH가 연구용 research_h264_worker.py로 고정돼버린다(uploader.py가
    # 이 값을 import 시 1회만 읽는 모듈 전역변수라 이후 os.environ만 바꿔선 반영 안 됨).
    # 2단계는 실제 승인된 후보 worker를 검증해야 하므로 명시적으로 되돌린다.
    common.uploader.H264_WORKER_PATH = str(Path(__file__).resolve().parent / "h264_encoder_worker.py")
    if not Path(common.uploader.H264_WORKER_PATH).is_file():
        raise SystemExit(f"후보 worker 파일 없음: {common.uploader.H264_WORKER_PATH}")
    common.uploader._run_persistent_worker = common.routed_run_persistent_worker
    common._response_dir = "/dev/shm"
    common.verify_shm_locking()
    common.preflight_state_path("/dev/shm/codex_h264_stage2_preflight.json")

    videos = {
        "scene_a": common.load_frames(sys.argv[1]),
        "scene_b": common.load_frames(sys.argv[2]),
    }
    schedule = [
        (video_name, condition)
        for video_name in videos
        for condition in ("mp4v", "h264_shm_shm")
        for _ in range(ROUNDS)
    ]
    random.Random(SEED).shuffle(schedule)
    result_path = Path(sys.argv[3])
    rows = []
    started = time.monotonic()
    with result_path.open("w", encoding="utf-8") as output:
        common.write_row(
            output,
            {
                "kind": "preflight",
                "seed": SEED,
                "rounds": ROUNDS,
                "idle_sec": IDLE_SEC,
                "main_pid": MAIN_PID,
                "videos": list(videos),
            },
        )
        for sequence, (video_name, condition) in enumerate(schedule, 1):
            frames = videos[video_name]
            row = (
                run_mp4v(video_name, frames, sequence)
                if condition == "mp4v"
                else run_h264(video_name, frames, sequence)
            )
            rows.append(row)
            common.write_row(output, row)
            time.sleep(IDLE_SEC)
        common.write_row(output, summary(rows, started))


if __name__ == "__main__":
    try:
        main()
    finally:
        common.uploader._run_persistent_worker = common._original_run_persistent_worker
        common.uploader._stop_persistent_worker()
        common.cleanup_test_state_files()
        for path in (
            "/dev/shm/codex_h264_stage2_state.json",
            "/dev/shm/codex_h264_stage2_state.json.lock",
            "/dev/shm/codex_h264_stage2_preflight.json",
            "/dev/shm/codex_h264_stage2_preflight.json.lock",
        ):
            common.uploader._remove_quietly(path)
