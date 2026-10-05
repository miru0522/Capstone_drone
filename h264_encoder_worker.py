"""Jetson nvv4l2h264enc 전용 격리 작업 프로세스.

부모 uploader.py가 전체 프로세스에 제한시간을 적용한다. 이 파일에는 CUDA,
TensorRT, 카메라 모듈을 import하지 않아 인코더 정지의 영향 범위를 줄인다.
"""

import argparse
import ctypes
import json
import os
import signal
import sys
import tempfile
from types import SimpleNamespace


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-raw", required=True)
    parser.add_argument("--output-partial", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--frames", type=int, required=True)
    parser.add_argument("--fps", type=int, required=True)
    parser.add_argument("--bitrate", type=int, required=True)
    return parser.parse_args()


def _validate_args(args) -> int:
    for name in ("width", "height", "frames", "fps", "bitrate"):
        if getattr(args, name) <= 0:
            raise ValueError(f"{name}는 양수여야 함: {getattr(args, name)}")

    expected = args.width * args.height * 3 * args.frames
    actual = os.path.getsize(args.input_raw)
    if actual != expected:
        raise ValueError(f"raw 입력 크기 불일치: expected={expected}, actual={actual}")
    return args.width * args.height * 3


def _install_parent_death_signal() -> None:
    """Linux 부모가 종료되면 고아 NVENC 작업기가 남지 않게 SIGTERM을 받는다."""
    if not sys.platform.startswith("linux"):
        return

    parent_pid = os.getppid()
    if parent_pid == 1:
        raise RuntimeError("H264 worker 시작 전에 부모 프로세스가 종료됨")

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM) != 0:  # PR_SET_PDEATHSIG = 1
        errno = ctypes.get_errno()
        raise OSError(errno, "PR_SET_PDEATHSIG 설정 실패")

    if os.getppid() != parent_pid:
        os.kill(os.getpid(), signal.SIGTERM)


def encode(args) -> None:
    frame_bytes = _validate_args(args)

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
        f"! nvv4l2h264enc bitrate={args.bitrate} "
        "! h264parse ! qtmux ! filesink name=sink"
    )
    pipeline = Gst.parse_launch(description)
    appsrc = pipeline.get_by_name("src")
    sink = pipeline.get_by_name("sink")
    sink.set_property("location", args.output_partial)

    duration = Gst.SECOND // args.fps
    state_result = pipeline.set_state(Gst.State.PLAYING)
    if state_result == Gst.StateChangeReturn.FAILURE:
        raise RuntimeError("GStreamer pipeline PLAYING 전환 실패")

    try:
        with open(args.input_raw, "rb") as raw_file:
            for index in range(args.frames):
                payload = raw_file.read(frame_bytes)
                if len(payload) != frame_bytes:
                    raise RuntimeError(f"raw 프레임 조기 종료: index={index}")

                buffer = Gst.Buffer.new_allocate(None, frame_bytes, None)
                buffer.fill(0, payload)
                buffer.pts = index * duration
                buffer.dts = buffer.pts
                buffer.duration = duration
                flow = appsrc.emit("push-buffer", buffer)
                if flow != Gst.FlowReturn.OK:
                    raise RuntimeError(f"push-buffer 실패: index={index}, flow={flow}")

        flow = appsrc.emit("end-of-stream")
        if flow != Gst.FlowReturn.OK:
            raise RuntimeError(f"end-of-stream 전송 실패: flow={flow}")

        bus = pipeline.get_bus()
        message = bus.timed_pop_filtered(
            Gst.CLOCK_TIME_NONE,
            Gst.MessageType.ERROR | Gst.MessageType.EOS,
        )
        if message is None:
            raise RuntimeError("GStreamer 종료 메시지가 없음")
        if message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            raise RuntimeError(f"GStreamer 오류: {error}; debug={debug}")
    finally:
        pipeline.set_state(Gst.State.NULL)

    if not os.path.exists(args.output_partial) or os.path.getsize(args.output_partial) <= 0:
        raise RuntimeError("GStreamer 출력 파일이 비어 있음")


def _write_response(path: str, value: dict) -> None:
    directory = os.path.dirname(path) or "."
    fd, temp_path = tempfile.mkstemp(prefix=".h264-response-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as response_file:
            json.dump(value, response_file, ensure_ascii=False)
            response_file.flush()
            os.fsync(response_file.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def serve() -> int:
    """stdin JSON 요청을 순차 처리해 GStreamer import/초기화 비용을 재사용한다."""
    for line in sys.stdin:
        response_path = None
        try:
            request = json.loads(line)
            response_path = request.pop("response_path")
            encode(SimpleNamespace(**request))
            _write_response(response_path, {"ok": True})
        except Exception as exc:
            if response_path:
                _write_response(
                    response_path,
                    {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                )
            print(f"H264_WORKER_ERROR: {exc}", file=sys.stderr, flush=True)
            return 1
    return 0


def main() -> int:
    try:
        _install_parent_death_signal()
        if sys.argv[1:] == ["--serve"]:
            return serve()
        encode(_parse_args())
        return 0
    except Exception as exc:
        print(f"H264_WORKER_ERROR: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
