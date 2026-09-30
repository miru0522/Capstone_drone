"""로컬 주기 녹화용 Jetson H.264 격리 인코더."""

import argparse
import ctypes
import os
import signal
import sys


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-raw", required=True)
    parser.add_argument("--output-partial", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--frames", type=int, required=True)
    parser.add_argument("--fps", type=int, required=True)
    parser.add_argument("--bitrate", type=int, required=True)
    return parser.parse_args()


def install_parent_death_signal() -> None:
    """부모 main.py가 종료되면 고아 인코더도 즉시 종료한다."""
    parent_pid = os.getppid()
    if parent_pid == 1:
        raise RuntimeError("부모 프로세스가 이미 종료됨")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM) != 0:  # PR_SET_PDEATHSIG
        errno = ctypes.get_errno()
        raise OSError(errno, "PR_SET_PDEATHSIG 설정 실패")
    if os.getppid() != parent_pid:
        os.kill(os.getpid(), signal.SIGTERM)


def encode(args) -> None:
    for name in ("width", "height", "frames", "fps", "bitrate"):
        if getattr(args, name) <= 0:
            raise ValueError(f"{name}는 양수여야 함")

    frame_bytes = args.width * args.height * 3
    expected_bytes = frame_bytes * args.frames
    actual_bytes = os.path.getsize(args.input_raw)
    if actual_bytes != expected_bytes:
        raise ValueError(
            f"raw 크기 불일치: expected={expected_bytes}, actual={actual_bytes}"
        )

    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst

    Gst.init(None)
    description = (
        "appsrc name=src is-live=true block=true format=time "
        f"caps=video/x-raw,format=BGR,width={args.width},height={args.height},"
        f"framerate={args.fps}/1 "
        "! videoconvert ! video/x-raw,format=NV12 "
        "! nvvidconv ! video/x-raw(memory:NVMM),format=NV12 "
        f"! nvv4l2h264enc bitrate={args.bitrate} insert-sps-pps=true "
        "! h264parse ! qtmux ! filesink name=sink"
    )
    pipeline = Gst.parse_launch(description)
    appsrc = pipeline.get_by_name("src")
    sink = pipeline.get_by_name("sink")
    sink.set_property("location", args.output_partial)

    duration = Gst.SECOND // args.fps
    if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
        raise RuntimeError("GStreamer PLAYING 전환 실패")

    try:
        with open(args.input_raw, "rb") as raw_file:
            for index in range(args.frames):
                payload = raw_file.read(frame_bytes)
                if len(payload) != frame_bytes:
                    raise RuntimeError(f"raw 프레임 조기 종료: {index}")
                buffer = Gst.Buffer.new_allocate(None, frame_bytes, None)
                buffer.fill(0, payload)
                buffer.pts = index * duration
                buffer.dts = buffer.pts
                buffer.duration = duration
                flow = appsrc.emit("push-buffer", buffer)
                if flow != Gst.FlowReturn.OK:
                    raise RuntimeError(f"push-buffer 실패: {index}, {flow}")

        flow = appsrc.emit("end-of-stream")
        if flow != Gst.FlowReturn.OK:
            raise RuntimeError(f"end-of-stream 실패: {flow}")
        message = pipeline.get_bus().timed_pop_filtered(
            Gst.CLOCK_TIME_NONE,
            Gst.MessageType.ERROR | Gst.MessageType.EOS,
        )
        if message is None:
            raise RuntimeError("GStreamer 종료 메시지 없음")
        if message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            raise RuntimeError(f"GStreamer 오류: {error}; debug={debug}")
    finally:
        pipeline.set_state(Gst.State.NULL)

    if not os.path.exists(args.output_partial) or os.path.getsize(args.output_partial) <= 0:
        raise RuntimeError("출력 파일이 비어 있음")


def main() -> int:
    try:
        install_parent_death_signal()
        encode(parse_args())
        return 0
    except Exception as exc:
        print(f"PERIODIC_H264_ENCODER_ERROR: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
