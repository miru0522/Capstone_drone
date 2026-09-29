"""동일 원본(scene_b, 폭력 라벨)을 mp4v/H264(1.2·2·4Mbps) 조건별로 인코딩해
실제 운영 AI서버(/analyze-video)에 전송하고 VideoMAE 판정을 비교한다.

사용자 승인 하에 실행하는 서버 판정 시험 — 실제 이상 이벤트 로그와 서버 부하를
유발하므로 임의로 반복 실행하지 않는다. mp4v 2회 + H264(1.2/2/4Mbps) 각 2회 = 8회.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

import stage1_storage_factorial as common


ANALYZE_URL = "http://203.249.90.3:8031/analyze-video"
IDLE_SEC = 3.0


def send(path):
    started = time.monotonic()
    with open(path, "rb") as f:
        files = {"video": (os.path.basename(path), f, "video/mp4")}
        resp = requests.post(ANALYZE_URL, files=files, timeout=180)
    elapsed = time.monotonic() - started
    body = None
    try:
        body = resp.json()
    except ValueError:
        body = {"raw_text": resp.text[:500]}
    return {
        "status_code": resp.status_code,
        "elapsed_sec": elapsed,
        "body": body,
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: quality_server_judgment_test.py VIDEO_PATH")

    common.uploader.H264_WORKER_PATH = str(
        Path("/tmp/codex_h264_stage2_stability/h264_encoder_worker.py")
    )
    if not Path(common.uploader.H264_WORKER_PATH).is_file():
        raise SystemExit(f"승인된 worker 파일 없음: {common.uploader.H264_WORKER_PATH}")
    common.uploader._run_persistent_worker = common.routed_run_persistent_worker
    common._response_dir = "/dev/shm"
    common.verify_shm_locking()
    common.preflight_state_path("/dev/shm/codex_quality_test_preflight.json")

    frames = common.load_frames(sys.argv[1])

    conditions = [
        ("mp4v", None),
        ("h264_900k", 900_000),
        ("h264_600k", 600_000),
    ]

    results = []
    try:
        for cond_name, bitrate in conditions:
            for repeat in (1,):
                if cond_name == "mp4v":
                    output_path = common.uploader._encode_frames_mp4v(frames, 9)
                else:
                    common.uploader.H264_BITRATE = bitrate
                    state_path = "/dev/shm/codex_quality_test_state.json"
                    common.uploader.H264_STATE_PATH = state_path
                    output_path = common.uploader._encode_frames_h264(frames, 9)

                size_bytes = os.path.getsize(output_path)
                try:
                    outcome = send(output_path)
                finally:
                    common.uploader._remove_quietly(output_path)

                row = {
                    "condition": cond_name,
                    "repeat": repeat,
                    "size_bytes": size_bytes,
                    **outcome,
                }
                results.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
                time.sleep(IDLE_SEC)
    finally:
        common.uploader._run_persistent_worker = common._original_run_persistent_worker
        common.uploader._stop_persistent_worker()
        common.cleanup_test_state_files()
        for path in (
            "/dev/shm/codex_quality_test_state.json",
            "/dev/shm/codex_quality_test_state.json.lock",
            "/dev/shm/codex_quality_test_preflight.json",
            "/dev/shm/codex_quality_test_preflight.json.lock",
        ):
            common.uploader._remove_quietly(path)

    print(json.dumps({"kind": "done", "total": len(results)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
