"""
h264enctest.py — Jetson 하드웨어 H.264 인코더(nvv4l2h264enc) 안정성 테스트 모듈.

배경:
  uploader.py의 encode_frames_to_mp4()는 2026-08-31 커밋(7123cfa8)에서
  "OpenCV cv2.VideoWriter + GStreamer(CAP_GSTREAMER) 경로가 write/release
  단계에서 hang된다"는 이유로 mp4v(소프트웨어) 인코딩으로 교체됐다.

  2026-09-26 재검증(연구 요청에 따른 것): 동일한 하드웨어 파이프라인
  (nvv4l2h264enc + qtmux 포함)을 gst-launch-1.0으로 직접 돌리면
  타임아웃 없이 3.9초 만에 정상 종료(EOS 수신, 파일 정상 생성)됨을 확인했다.
  즉 하드웨어·qtmux 자체는 문제가 없고, OpenCV의 GStreamer 래퍼(특히
  백그라운드 스레드에서 GLib MainLoop 없이 호출되는 상황)가 원인으로 추정된다.

  이 모듈은 OpenCV를 거치지 않고 PyGObject(gi.repository.Gst)로 파이프라인을
  직접 제어해, EOS/에러를 버스 메시지로 명시적으로 확인하고 타임아웃을 걸어
  hang을 원천적으로 방지한다.

주의:
  - 이 파일은 실험/검증용이며 uploader.py의 기존 encode_frames_to_mp4()를
    대체하지 않는다. 운영 경로에는 아직 연결되지 않았다.
  - 실기 검증 전 임의로 main.py/uploader.py에 연결하지 말 것.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Protocol

import numpy as np

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402

logger = logging.getLogger("h264enctest")

_gst_init_lock = threading.Lock()
_gst_initialized = False


def _ensure_gst_init() -> None:
    global _gst_initialized
    with _gst_init_lock:
        if not _gst_initialized:
            Gst.init(None)
            _gst_initialized = True


class HWEncodeError(RuntimeError):
    """하드웨어 인코딩 실패(에러 또는 타임아웃 의심 hang) 시 발생."""


class _HasFrame(Protocol):
    frame: np.ndarray


def encode_frames_to_mp4_hw(
    frames: List[_HasFrame],
    fps: int = 9,
    bitrate: int = 4_000_000,
    timeout_sec: float = 15.0,
    out_path: Optional[str] = None,
) -> str:
    """
    프레임 리스트(각 원소는 .frame 속성에 BGR np.ndarray를 가짐)를
    하드웨어(nvv4l2h264enc) H.264 mp4 임시파일로 인코딩해 경로를 반환한다.

    실패(GStreamer 에러) 또는 timeout_sec 안에 EOS를 못 받으면(hang 의심)
    HWEncodeError를 던진다 — 무한 대기하지 않는다.

    호출자가 반환된 파일을 삭제할 책임이 있다.
    """
    if not frames:
        raise ValueError("encode_frames_to_mp4_hw: 빈 프레임 리스트")

    t_start = time.time()
    _ensure_gst_init()

    h, w = frames[0].frame.shape[:2]

    if out_path is None:
        fd, path = tempfile.mkstemp(suffix=".mp4", prefix="hwenc_test_")
        os.close(fd)
        os.remove(path)  # filesink가 새로 생성하게 한다 (기존 0바이트 파일 방지)
    else:
        path = out_path
        if os.path.exists(path):
            os.remove(path)

    pipeline_str = (
        "appsrc name=src is-live=true block=true format=time "
        f"caps=video/x-raw,format=BGR,width={w},height={h},framerate={fps}/1 ! "
        "videoconvert ! video/x-raw,format=NV12 ! "
        "nvvidconv ! video/x-raw(memory:NVMM),format=NV12 ! "
        f"nvv4l2h264enc bitrate={bitrate} ! "
        f"h264parse ! qtmux ! filesink location={path}"
    )

    pipeline = Gst.parse_launch(pipeline_str)
    appsrc = pipeline.get_by_name("src")
    if appsrc is None:
        raise HWEncodeError("appsrc 엘리먼트를 찾을 수 없음 (파이프라인 파싱 실패)")

    loop = GLib.MainLoop()
    result: dict = {"error": None}

    def on_message(_bus, message):
        mtype = message.type
        if mtype == Gst.MessageType.EOS:
            loop.quit()
        elif mtype == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            result["error"] = f"{err}: {debug}"
            loop.quit()
        return True

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_message)

    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        pipeline.set_state(Gst.State.NULL)
        raise HWEncodeError("파이프라인을 PLAYING 상태로 전환 실패")

    # 버스 메시지(EOS/ERROR)를 실제로 받으려면 MainLoop이 돌고 있어야 한다.
    # 별도 스레드에서 돌리고, 이 스레드에서는 join(timeout)으로 hang을 방지한다.
    runner = threading.Thread(target=loop.run, daemon=True, name="h264enctest-mainloop")
    runner.start()

    try:
        duration = Gst.SECOND // fps
        pts = 0
        for entry in frames:
            data = np.ascontiguousarray(entry.frame).tobytes()
            buf = Gst.Buffer.new_allocate(None, len(data), None)
            buf.fill(0, data)
            buf.pts = pts
            buf.duration = duration
            pts += duration
            flow = appsrc.emit("push-buffer", buf)
            if flow != Gst.FlowReturn.OK:
                raise HWEncodeError(f"push-buffer 실패: {flow}")
        appsrc.emit("end-of-stream")
    except Exception:
        loop.quit()
        pipeline.set_state(Gst.State.NULL)
        try:
            os.remove(path)
        except OSError:
            pass
        raise

    runner.join(timeout=timeout_sec)
    hung = runner.is_alive()

    if hung:
        logger.error("[h264enctest] EOS 미수신 - %.1f초 타임아웃, hang 의심", timeout_sec)
        loop.quit()
        pipeline.set_state(Gst.State.NULL)
        try:
            os.remove(path)
        except OSError:
            pass
        raise HWEncodeError(f"인코딩 타임아웃({timeout_sec}s) - hang 의심")

    pipeline.set_state(Gst.State.NULL)

    if result["error"]:
        try:
            os.remove(path)
        except OSError:
            pass
        raise HWEncodeError(f"GStreamer 에러: {result['error']}")

    if not os.path.exists(path) or os.path.getsize(path) <= 0:
        raise HWEncodeError("인코딩 결과 파일이 비어 있음(0바이트 또는 미생성)")

    elapsed = time.time() - t_start
    logger.info(
        "h264(HW) 인코딩 완료: frames=%d, fps=%d, size=%d bytes, elapsed=%.3fs",
        len(frames), fps, os.path.getsize(path), elapsed,
    )

    return path


@dataclass
class _FakeFrameEntry:
    frame: np.ndarray


def _load_frames_from_video(path: str, target_w: int, target_h: int) -> List[_FakeFrameEntry]:
    import cv2

    cap = cv2.VideoCapture(path)
    frames: List[_FakeFrameEntry] = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame.shape[1] != target_w or frame.shape[0] != target_h:
            frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
        frames.append(_FakeFrameEntry(frame=frame))
    cap.release()
    return frames


def _self_test(video_path: str, repeats: int, width: int, height: int, fps: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("자체 시험 시작: video=%s repeats=%d size=%dx%d fps=%d", video_path, repeats, width, height, fps)

    frames = _load_frames_from_video(video_path, width, height)
    if not frames:
        logger.error("영상에서 프레임을 못 읽음: %s", video_path)
        raise SystemExit(1)
    logger.info("프레임 로드 완료: %d개", len(frames))

    ok = 0
    fail = 0
    for i in range(1, repeats + 1):
        t0 = time.time()
        try:
            out = encode_frames_to_mp4_hw(frames, fps=fps)
            size = os.path.getsize(out)
            os.remove(out)
            elapsed = time.time() - t0
            logger.info("[%d/%d] 성공: %.3fs, %d bytes", i, repeats, elapsed, size)
            ok += 1
        except HWEncodeError as e:
            elapsed = time.time() - t0
            logger.error("[%d/%d] 실패(%.3fs 경과): %s", i, repeats, elapsed, e)
            fail += 1

    logger.info("자체 시험 종료: 성공 %d / 실패 %d (총 %d회)", ok, fail, repeats)
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="h264enctest 자체 시험 (하드웨어 인코더 반복 안정성 확인)")
    ap.add_argument("video", help="테스트용 mp4 경로")
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=9)
    args = ap.parse_args()

    _self_test(args.video, args.repeats, args.width, args.height, args.fps)
