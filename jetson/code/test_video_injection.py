"""
test_video_injection.py
main.py를 건드리지 않고, 준비된 테스트 영상을 RingBuffer에 직접 주입해
AnomalyPipeline(YOLOv5n+WideBranchNet)의 실제 추론 결과를 확인하는
독립 테스트 스크립트.

main.py는 완전히 별개의 프로세스로 그대로 두고, 이 스크립트는 같은
모듈(ring_buffer, anomaly_model, uploader)만 재사용해서 독립 실행됨.

사용법:
  python3 test_video_injection.py <영상경로> [--upload]

  --upload 옵션을 주면, 계산된 점수와 함께 실제 서버(/analyze-video)로
  전송까지 시도함 (기본은 점수 계산만 하고 전송 안 함).
"""

import sys
import argparse
import logging

import cv2
import numpy as np

from ring_buffer import RingBuffer, FrameEntry, FPS, BUFFER_MAXLEN, INFER_WINDOW_LEN
from anomaly_model import AnomalyPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_video_injection")


def load_video_resampled_to_9fps(video_path: str) -> list:
    """영상을 읽어서 9fps에 맞게 프레임을 리샘플링(간격 샘플링)해서 리스트로 반환."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"영상을 열 수 없습니다: {video_path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    logger.info(f"원본 영상: fps={src_fps:.2f}, 총 프레임={total_frames}")

    all_frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        all_frames.append(frame)
    cap.release()
    logger.info(f"실제로 읽은 프레임 수: {len(all_frames)}")

    # 9fps로 리샘플링 (원본fps 대비 간격 샘플링)
    if src_fps <= 0:
        src_fps = 30.0
    step = src_fps / FPS
    resampled = []
    idx = 0.0
    while int(idx) < len(all_frames):
        resampled.append(all_frames[int(idx)])
        idx += step
    logger.info(f"9fps로 리샘플링 후 프레임 수: {len(resampled)}")
    return resampled


def main():
    parser = argparse.ArgumentParser(description="테스트 영상을 RingBuffer에 주입해 추론 결과 확인")
    parser.add_argument("video_path", help="테스트 영상 파일 경로")
    parser.add_argument("--upload", action="store_true", help="계산 후 실제 서버로 전송도 시도")
    args = parser.parse_args()

    logger.info(f"테스트 영상 로드 중: {args.video_path}")
    frames = load_video_resampled_to_9fps(args.video_path)

    if len(frames) < INFER_WINDOW_LEN:
        logger.warning(
            f"리샘플링된 프레임({len(frames)}개)이 추론 윈도우({INFER_WINDOW_LEN}개)보다 적습니다. "
            f"마지막 프레임을 반복해서 채웁니다."
        )
        while len(frames) < INFER_WINDOW_LEN:
            frames.append(frames[-1])

    # RingBuffer 생성 및 프레임 주입 (main.py와 완전히 독립된 별도 인스턴스)
    buffer = RingBuffer(maxlen=BUFFER_MAXLEN)
    for f in frames:
        buffer.push(f)
    logger.info(f"RingBuffer에 {len(frames)}프레임 주입 완료")

    if not buffer.is_ready_for_inference():
        logger.error("RingBuffer가 추론 준비 상태가 아닙니다 (프레임 부족)")
        sys.exit(1)

    window = buffer.get_latest_window(INFER_WINDOW_LEN)
    logger.info(f"추론 윈도우 shape: {window.shape}")

    logger.info("AnomalyPipeline 초기화 중 (YOLOv5n + WideBranchNet 엔진 로드)...")
    pipeline = AnomalyPipeline()

    logger.info("추론 실행 중...")
    score = pipeline.compute_score(window)

    print("=" * 50)
    print(f" 테스트 영상 추론 결과")
    print(f" 파일: {args.video_path}")
    print(f" anomaly_score = {score:.4f}  (0=정상, 1=이상)")
    print("=" * 50)

    if args.upload:
        logger.info("서버로 실제 업로드 시도 중 (upload_clip_sync)...")
        from uploader import upload_clip_sync
        full_snapshot = buffer.get_full_buffer()
        result = upload_clip_sync(full_snapshot, anomaly_score=score)
        if result:
            logger.info(f"서버 응답: {result}")
        else:
            logger.warning("서버 응답 없음/실패")


if __name__ == "__main__":
    main()
