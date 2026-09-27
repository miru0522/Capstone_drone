"""전체 저장 영상과 고정 대표 영상으로 H264 600kbps 채택 지연을 검증한다."""

import gc
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

import stage1_storage_factorial as common
import stage2_stability as stage2


SEED = int(os.environ.get("H264_600_SEED", "20260927"))
ALL_VIDEO_REPEATS = int(os.environ.get("H264_600_ALL_REPEATS", "2"))
REFERENCE_REPEATS = int(os.environ.get("H264_600_REFERENCE_REPEATS", "20"))
IDLE_SEC = float(os.environ.get("H264_600_IDLE_SEC", "8.0"))
REQUIRED_PER_CONDITION = int(os.environ.get("H264_600_REQUIRED_PER_CONDITION", "100"))
BITRATE = 600_000
VIDEO_SUFFIXES = {".mp4", ".avi", ".mkv"}


def stats(values):
    return {
        "count": len(values),
        "mean_sec": statistics.mean(values),
        "p50_sec": statistics.median(values),
        "p95_sec": common.percentile(values, 95),
        "max_sec": max(values),
    }


def discover_videos(video_root):
    videos = sorted(
        path.resolve()
        for path in video_root.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    )
    if not videos:
        raise RuntimeError(f"시험 영상 없음: {video_root}")
    return videos


def build_schedule(video_root, videos, references):
    schedule = []
    for path in videos:
        name = path.relative_to(video_root).as_posix()
        for repeat in range(1, ALL_VIDEO_REPEATS + 1):
            for condition in ("mp4v", "h264_600k"):
                schedule.append(
                    {
                        "video": name,
                        "path": str(path),
                        "phase": "all_videos",
                        "repeat": repeat,
                        "condition": condition,
                    }
                )
    for path in references:
        name = path.relative_to(video_root).as_posix()
        for repeat in range(1, REFERENCE_REPEATS + 1):
            for condition in ("mp4v", "h264_600k"):
                schedule.append(
                    {
                        "video": name,
                        "path": str(path),
                        "phase": "reference_repeat",
                        "repeat": repeat,
                        "condition": condition,
                    }
                )
    random.Random(SEED).shuffle(schedule)
    return schedule


def build_summary(rows, started, videos, references):
    result = {
        "kind": "summary",
        "elapsed_sec": time.monotonic() - started,
        "bitrate": BITRATE,
        "all_video_count": len(videos),
        "all_video_repeats": ALL_VIDEO_REPEATS,
        "reference_repeats": REFERENCE_REPEATS,
        "idle_sec": IDLE_SEC,
        "total_encode_count": len(rows),
        "conditions": {},
        "reference_conditions": {},
        "worker_pids": sorted(
            {
                row["worker"]["pid"]
                for row in rows
                if row.get("worker") is not None
            }
        ),
        "main_pid_all_alive": all(row["main_pid_alive"] for row in rows),
        "decoded_all": all(row["decoded_frames"] == 81 for row in rows),
        "orphan_paths": sorted(
            str(path)
            for pattern in ("anomaly_clip_*.bgr", "anomaly_clip_*.response.json")
            for path in Path("/dev/shm").glob(pattern)
        ),
    }
    for condition in ("mp4v", "h264_600k"):
        selected = [row["total_sec"] for row in rows if row["condition"] == condition]
        result["conditions"][condition] = stats(selected)

    mp4v = result["conditions"]["mp4v"]
    h264 = result["conditions"]["h264_600k"]
    result["improvement_percent"] = {
        "p50": (1.0 - h264["p50_sec"] / mp4v["p50_sec"]) * 100.0,
        "p95": (1.0 - h264["p95_sec"] / mp4v["p95_sec"]) * 100.0,
    }

    for reference in references:
        name = reference.relative_to(reference.parents[1]).as_posix()
        matching_names = {
            row["video"] for row in rows if row["path"] == str(reference)
        }
        if len(matching_names) != 1:
            raise RuntimeError(f"대표 영상 이름 확인 실패: {reference}")
        name = matching_names.pop()
        per_condition = {}
        for condition in ("mp4v", "h264_600k"):
            values = [
                row["total_sec"]
                for row in rows
                if row["video"] == name and row["condition"] == condition
            ]
            per_condition[condition] = stats(values)
        per_condition["improvement_percent"] = {
            "p50": (
                1.0
                - per_condition["h264_600k"]["p50_sec"]
                / per_condition["mp4v"]["p50_sec"]
            )
            * 100.0,
            "p95": (
                1.0
                - per_condition["h264_600k"]["p95_sec"]
                / per_condition["mp4v"]["p95_sec"]
            )
            * 100.0,
        }
        result["reference_conditions"][name] = per_condition
    return result


def main():
    if len(sys.argv) != 5:
        raise SystemExit(
            "usage: stage2_600_acceptance.py VIDEO_ROOT REFERENCE_A "
            "REFERENCE_B RESULT_JSONL"
        )
    video_root = Path(sys.argv[1]).resolve()
    references = [Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()]
    result_path = Path(sys.argv[4])
    videos = discover_videos(video_root)
    for reference in references:
        if reference not in videos:
            raise RuntimeError(f"대표 영상이 전체 목록에 없음: {reference}")

    common.MAIN_PID = stage2.MAIN_PID
    common.uploader.H264_BITRATE = BITRATE
    common.uploader.H264_WORKER_PATH = str(
        Path(__file__).resolve().parent / "h264_encoder_worker.py"
    )
    if not Path(common.uploader.H264_WORKER_PATH).is_file():
        raise RuntimeError(f"승인 worker 없음: {common.uploader.H264_WORKER_PATH}")
    common.uploader._run_persistent_worker = common.routed_run_persistent_worker
    common._response_dir = "/dev/shm"
    common.verify_shm_locking()
    common.preflight_state_path("/dev/shm/codex_h264_600_preflight.json")

    schedule = build_schedule(video_root, videos, references)
    expected_per_condition = len(videos) * ALL_VIDEO_REPEATS + len(references) * REFERENCE_REPEATS
    if expected_per_condition != REQUIRED_PER_CONDITION:
        raise RuntimeError(
            f"조건별 표본 수 불일치: actual={expected_per_condition}, "
            f"required={REQUIRED_PER_CONDITION}; "
            f"videos={len(videos)}"
        )

    rows = []
    started = time.monotonic()
    with result_path.open("w", encoding="utf-8") as output:
        common.write_row(
            output,
            {
                "kind": "preflight",
                "seed": SEED,
                "bitrate": BITRATE,
                "video_root": str(video_root),
                "video_count": len(videos),
                "all_video_repeats": ALL_VIDEO_REPEATS,
                "reference_repeats": REFERENCE_REPEATS,
                "idle_sec": IDLE_SEC,
                "expected_per_condition": expected_per_condition,
                "references": [str(path) for path in references],
            },
        )
        for sequence, job in enumerate(schedule, 1):
            load_started = time.monotonic()
            frames = common.load_frames(job["path"])
            load_sec = time.monotonic() - load_started
            row = (
                stage2.run_mp4v(job["video"], frames, sequence)
                if job["condition"] == "mp4v"
                else stage2.run_h264(job["video"], frames, sequence)
            )
            row.update(job)
            row["sequence"] = sequence
            row["load_sec"] = load_sec
            row["bitrate"] = None if job["condition"] == "mp4v" else BITRATE
            rows.append(row)
            common.write_row(output, row)
            del frames
            gc.collect()
            time.sleep(IDLE_SEC)
        common.write_row(
            output, build_summary(rows, started, videos, references)
        )


if __name__ == "__main__":
    try:
        main()
    finally:
        common.uploader._run_persistent_worker = common._original_run_persistent_worker
        common.uploader._stop_persistent_worker()
        common.cleanup_test_state_files()
        for path in (
            "/dev/shm/codex_h264_600_preflight.json",
            "/dev/shm/codex_h264_600_preflight.json.lock",
            "/dev/shm/codex_h264_stage2_state.json",
            "/dev/shm/codex_h264_stage2_state.json.lock",
        ):
            common.uploader._remove_quietly(path)
