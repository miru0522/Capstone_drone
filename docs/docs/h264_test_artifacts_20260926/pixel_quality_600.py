"""전체 영상의 mp4v/H264 600 kbps 픽셀 품질을 같은 원본 프레임으로 비교한다."""

import json
import os
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np

import stage1_storage_factorial as common


BITRATE = 600_000
EXPECTED_FRAMES = 81
VIDEO_SUFFIXES = {".mp4", ".avi", ".mkv"}


def ssim_bgr(reference, decoded):
    """11x11 Gaussian 창을 사용하는 채널 평균 SSIM을 계산한다."""
    first = reference.astype(np.float32)
    second = decoded.astype(np.float32)
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    mu_first = cv2.GaussianBlur(first, (11, 11), 1.5)
    mu_second = cv2.GaussianBlur(second, (11, 11), 1.5)
    mu_first_sq = mu_first * mu_first
    mu_second_sq = mu_second * mu_second
    mu_product = mu_first * mu_second
    sigma_first_sq = cv2.GaussianBlur(first * first, (11, 11), 1.5) - mu_first_sq
    sigma_second_sq = cv2.GaussianBlur(second * second, (11, 11), 1.5) - mu_second_sq
    sigma_product = cv2.GaussianBlur(first * second, (11, 11), 1.5) - mu_product
    numerator = (2.0 * mu_product + c1) * (2.0 * sigma_product + c2)
    denominator = (mu_first_sq + mu_second_sq + c1) * (
        sigma_first_sq + sigma_second_sq + c2
    )
    return float(np.mean(numerator / denominator))


def decode_frames(path):
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise RuntimeError(f"출력 영상 열기 실패: {path}")
    frames = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame is None or frame.size == 0:
            capture.release()
            raise RuntimeError(f"빈 디코딩 프레임: {path}, index={len(frames)}")
        frames.append(frame)
    capture.release()
    if len(frames) != EXPECTED_FRAMES:
        raise RuntimeError(
            f"디코딩 프레임 수 불일치: {path}, actual={len(frames)}, "
            f"expected={EXPECTED_FRAMES}"
        )
    return frames


def measure(condition, source_entries):
    output_path = (
        common.uploader._encode_frames_mp4v(source_entries, 9)
        if condition == "mp4v"
        else common.uploader._encode_frames_h264(source_entries, 9)
    )
    try:
        decoded = decode_frames(output_path)
        psnr_values = []
        ssim_values = []
        for source_entry, output_frame in zip(source_entries, decoded):
            source_frame = source_entry.frame
            if output_frame.shape != source_frame.shape:
                raise RuntimeError(
                    f"프레임 크기 불일치: source={source_frame.shape}, "
                    f"decoded={output_frame.shape}"
                )
            psnr_values.append(float(cv2.PSNR(source_frame, output_frame)))
            ssim_values.append(ssim_bgr(source_frame, output_frame))
        return {
            "condition": condition,
            "size_bytes": os.path.getsize(output_path),
            "frame_count": len(decoded),
            "psnr_mean_db": statistics.mean(psnr_values),
            "psnr_min_db": min(psnr_values),
            "ssim_mean": statistics.mean(ssim_values),
            "ssim_min": min(ssim_values),
        }
    finally:
        common.uploader._remove_quietly(output_path)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: pixel_quality_600.py VIDEO_ROOT RESULT_JSONL")
    video_root = Path(sys.argv[1]).resolve()
    result_path = Path(sys.argv[2]).resolve()
    videos = sorted(
        path
        for path in video_root.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    )
    if not videos:
        raise RuntimeError(f"시험 영상 없음: {video_root}")

    common.uploader.H264_BITRATE = BITRATE
    common.uploader.H264_WORKER_PATH = str(
        Path(__file__).resolve().parent / "h264_encoder_worker.py"
    )
    common.uploader.H264_RAW_DIR = "/dev/shm"
    common.uploader.H264_STATE_PATH = "/dev/shm/codex_h264_quality_state.json"
    common.uploader._run_persistent_worker = common.routed_run_persistent_worker
    common._response_dir = "/dev/shm"
    common.verify_shm_locking()
    common.preflight_state_path("/dev/shm/codex_h264_quality_preflight.json")

    rows = []
    with result_path.open("w", encoding="utf-8") as output:
        common.write_row(
            output,
            {
                "kind": "preflight",
                "video_root": str(video_root),
                "video_count": len(videos),
                "bitrate": BITRATE,
                "expected_frames": EXPECTED_FRAMES,
            },
        )
        for video in videos:
            frames = common.load_frames(str(video))
            if len(frames) != EXPECTED_FRAMES:
                raise RuntimeError(f"원본 프레임 수 불일치: {video}")
            for condition in ("mp4v", "h264_600k"):
                row = measure(condition, frames)
                row.update(
                    {
                        "kind": "quality",
                        "video": video.relative_to(video_root).as_posix(),
                    }
                )
                rows.append(row)
                common.write_row(output, row)

        summary = {"kind": "summary", "conditions": {}}
        for condition in ("mp4v", "h264_600k"):
            selected = [row for row in rows if row["condition"] == condition]
            summary["conditions"][condition] = {
                "video_count": len(selected),
                "psnr_mean_db": statistics.mean(
                    row["psnr_mean_db"] for row in selected
                ),
                "psnr_worst_video_mean_db": min(
                    row["psnr_mean_db"] for row in selected
                ),
                "psnr_worst_frame_db": min(row["psnr_min_db"] for row in selected),
                "ssim_mean": statistics.mean(row["ssim_mean"] for row in selected),
                "ssim_worst_video_mean": min(
                    row["ssim_mean"] for row in selected
                ),
                "ssim_worst_frame": min(row["ssim_min"] for row in selected),
                "all_video_means_pass": all(
                    row["psnr_mean_db"] >= 30.0 and row["ssim_mean"] >= 0.95
                    for row in selected
                ),
            }
        common.write_row(output, summary)


if __name__ == "__main__":
    try:
        main()
    finally:
        common.uploader._run_persistent_worker = common._original_run_persistent_worker
        common.uploader._stop_persistent_worker()
        common.cleanup_test_state_files()
        for path in (
            "/dev/shm/codex_h264_quality_state.json",
            "/dev/shm/codex_h264_quality_state.json.lock",
            "/dev/shm/codex_h264_quality_preflight.json",
            "/dev/shm/codex_h264_quality_preflight.json.lock",
        ):
            common.uploader._remove_quietly(path)
