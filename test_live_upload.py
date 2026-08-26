"""
실시간 카메라 -> 링버퍼 -> 강제 트리거(1회) -> 서버 업로드 테스트.
main.py 원본은 건드리지 않고, 여기서만 detect_anomaly를 강제 트리거로 대체.
"""
import time
import logging

from ring_buffer import RingBuffer, FPS, BUFFER_MAXLEN, INFER_WINDOW_LEN
from uploader import upload_clip_async
from main import create_gstreamer_pipeline

import cv2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_live_upload")


def main():
    buffer = RingBuffer(maxlen=BUFFER_MAXLEN)
    pipeline = create_gstreamer_pipeline()

    logger.info("CSI 카메라 여는 중...")
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        raise RuntimeError("CSI 카메라를 열 수 없습니다 (GStreamer 파이프라인 실패)")
    logger.info("✅ 카메라 열림")

    frame_interval = 1.0 / FPS
    next_tick = time.time()
    triggered = False
    upload_thread = None

    try:
        logger.info(f"실시간 캡처 시작 (FPS={FPS}). 버퍼가 {BUFFER_MAXLEN}프레임 찰 때까지 대기 후 1회 강제 업로드합니다.")
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("프레임 읽기 실패, 재시도")
                time.sleep(0.1)
                continue

            buffer.push(frame)
            fill = buffer.get_fill_ratio()

            if not triggered:
                logger.info(f"버퍼 채움: {len(buffer)}/{BUFFER_MAXLEN} ({fill*100:.0f}%)")

            # 버퍼가 완전히 찼으면 딱 한 번 강제 트리거
            if not triggered and len(buffer) >= BUFFER_MAXLEN:
                triggered = True
                logger.info("🚨 강제 트리거 발생 — 실시간 촬영분 버퍼 전체를 서버로 전송합니다.")
                snapshot = buffer.get_full_buffer()
                upload_thread = upload_clip_async(
                    snapshot,
                    anomaly_score=0.95,
                    trigger_timestamp=time.time(),
                )

            if triggered and upload_thread is not None and not upload_thread.is_alive():
                logger.info("업로드 스레드 종료 확인. 테스트 종료합니다.")
                break

            next_tick += frame_interval
            sleep_time = next_tick - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_tick = time.time()

    finally:
        cap.release()
        logger.info("카메라 해제 완료")


if __name__ == "__main__":
    main()
