"""P0-7 최소 서버 통합 시험 실행기.

기본 실행은 준비 상태만 검사한다. 실제 서버 전송에는 사용자의 명시 승인 뒤 전달할
확인 문자열과 --execute가 모두 필요하다. 한 프로세스에서 한 코덱 요청만 전송한다.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import cv2


ROOT = Path("/tmp/h264_600_reapply_20260930")
CANDIDATE = ROOT / "candidate"
OPERATION_DIR = Path("/home/hpc/drone_2026/code")
EVIDENCE = ROOT / "evidence"
DEFAULT_SOURCE = Path("/home/hpc/drone_2026/video/ucf/Assault006_x264.mp4")
DEFAULT_ENDPOINT = "http://203.249.90.3:8031/analyze-video"
EXPECTED_CONFIRMATION = "P0-7-APPROVED-2-REQUESTS"
TARGET_FRAMES = 81
TARGET_WIDTH = 960
TARGET_HEIGHT = 540
TARGET_FPS = 9
TEST_SCORE = 0.654321


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("mp4v", "h264"), required=True)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--execute-confirm", default="")
    return parser.parse_args()


def load_sampled_frames(source: Path):
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError(f"영상을 열 수 없음: {source}")

    decoded = []
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            decoded.append(frame)
    finally:
        cap.release()

    if len(decoded) < TARGET_FRAMES:
        raise RuntimeError(
            f"원본 프레임 부족: decoded={len(decoded)}, required={TARGET_FRAMES}"
        )

    last = len(decoded) - 1
    indices = [round(i * last / (TARGET_FRAMES - 1)) for i in range(TARGET_FRAMES)]
    sampled = [
        cv2.resize(decoded[index], (TARGET_WIDTH, TARGET_HEIGHT), interpolation=cv2.INTER_AREA)
        for index in indices
    ]
    digest = hashlib.sha256()
    for frame in sampled:
        digest.update(frame.tobytes())
    return sampled, indices, len(decoded), digest.hexdigest()


def probe_video(path: str):
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,avg_frame_rate,nb_frames,duration",
            "-of",
            "json",
            path,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(completed.stdout)


def configure_environment(args):
    os.environ.update(
        {
            "PYTHONPATH": f"{CANDIDATE}:{OPERATION_DIR}",
            "UPLOAD_MODE": "B",
            "DRONE_ID": "DR-01",
            "ANALYZE_URL": args.endpoint,
            "CLIP_ENCODER": args.mode,
            "H264_BITRATE": "600000",
            "H264_WORKER_PATH": str(CANDIDATE / "h264_encoder_worker.py"),
            "H264_RAW_DIR": "/dev/shm",
            "H264_STATE_PATH": f"/tmp/p0_7_h264_state_{args.mode}.json",
            "H264_WORKER_LOG_PATH": f"/tmp/p0_7_h264_worker_{args.mode}.log",
        }
    )
    sys.path.insert(0, str(CANDIDATE))
    sys.path.insert(1, str(OPERATION_DIR))


def main():
    args = parse_args()
    if args.endpoint != DEFAULT_ENDPOINT:
        raise SystemExit(f"승인 대상과 다른 endpoint: {args.endpoint}")

    frames, indices, decoded_count, frame_sha256 = load_sampled_frames(args.source)
    preparation = {
        "mode": args.mode,
        "source": str(args.source),
        "source_size_bytes": args.source.stat().st_size,
        "source_decoded_frames": decoded_count,
        "sampled_frames": len(frames),
        "sample_indices": indices,
        "sampled_raw_sha256": frame_sha256,
        "target_shape": [TARGET_HEIGHT, TARGET_WIDTH, 3],
        "target_fps": TARGET_FPS,
        "endpoint": args.endpoint,
        "drone_id": "DR-01",
        "anomaly_score": TEST_SCORE,
        "execute": args.execute,
    }
    if not args.execute:
        print(json.dumps({**preparation, "status": "DRY_RUN_PASS"}, ensure_ascii=False, indent=2))
        return
    if args.execute_confirm != EXPECTED_CONFIRMATION:
        raise SystemExit("실제 전송 확인 문자열이 없거나 일치하지 않음")

    configure_environment(args)
    import uploader
    from ring_buffer import FrameEntry

    entries = [FrameEntry(frame=frame, timestamp=float(i) / TARGET_FPS) for i, frame in enumerate(frames)]
    metrics = {"encode": {}, "request": {}}

    original_encode = uploader.encode_frames_to_mp4
    original_post = uploader.requests.post

    def measured_encode(frame_entries, fps=TARGET_FPS):
        started = time.time()
        path = original_encode(frame_entries, fps=fps)
        finished = time.time()
        metrics["encode"] = {
            "started_at": started,
            "finished_at": finished,
            "elapsed_sec": finished - started,
            "path": path,
            "size_bytes": os.path.getsize(path),
            "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "ffprobe": probe_video(path),
        }
        return path

    def measured_post(*post_args, **post_kwargs):
        started = time.time()
        response = original_post(*post_args, **post_kwargs)
        finished = time.time()
        metrics["request"] = {
            "started_at": started,
            "finished_at": finished,
            "elapsed_sec": finished - started,
            "status_code": response.status_code,
            "response_text": response.text,
            "response_headers": dict(response.headers),
        }
        return response

    uploader.encode_frames_to_mp4 = measured_encode
    uploader.requests.post = measured_post

    overall_started = time.time()
    response_json = uploader.upload_clip_sync(entries, anomaly_score=TEST_SCORE)
    overall_finished = time.time()
    result = {
        **preparation,
        "status": "PASS" if response_json is not None else "FAIL",
        "overall_started_at": overall_started,
        "overall_finished_at": overall_finished,
        "overall_elapsed_sec": overall_finished - overall_started,
        "metrics": metrics,
        "response_json": response_json,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    output = EVIDENCE / f"p0_server_integration_{args.mode}.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
