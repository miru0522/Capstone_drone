"""Jetson GStreamer 1.16.3 splitmuxsink의 요청 경계/마지막 조각 종료를 실측한다."""

import json
import time
from pathlib import Path

import cv2
import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst

from persistent_pipeline_test import BITRATE, FPS, FRAMES, HEIGHT, WIDTH, make_frames


Gst.init(None)


def drain_messages(bus, messages):
    while True:
        message = bus.pop()
        if message is None:
            return
        item = {"type": str(message.type), "src": message.src.get_name()}
        if message.type == Gst.MessageType.ELEMENT:
            structure = message.get_structure()
            item["structure"] = structure.to_string() if structure else None
        elif message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            item.update(error=str(error), debug=debug)
        messages.append(item)


def probe(path):
    capture = cv2.VideoCapture(str(path))
    count = 0
    first = None
    last = None
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            patch = frame[400:520, 20:260]
            mean = [float(value) for value in patch.mean(axis=(0, 1))]
            first = first or mean
            last = mean
            count += 1
    finally:
        capture.release()
    return {"frames": count, "first_mean_bgr": first, "last_mean_bgr": last}


def main():
    output_dir = Path("/tmp/h264_pipeline_reuse_20261002/splitmuxsink_probe")
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("fragment_*.mp4"):
        stale.unlink()
    pattern = output_dir / "fragment_%02d.mp4"
    description = (
        "appsrc name=src is-live=false block=false max-bytes=0 format=time "
        f"caps=video/x-raw,format=BGR,width={WIDTH},height={HEIGHT},framerate={FPS}/1 "
        "! videoconvert ! video/x-raw,format=NV12 "
        "! nvvidconv ! video/x-raw(memory:NVMM),format=NV12 "
        f"! nvv4l2h264enc name=enc bitrate={BITRATE} insert-sps-pps=true "
        "iframeinterval=256 idrinterval=256 "
        "! h264parse config-interval=-1 "
        "! splitmuxsink name=mux async-finalize=true muxer-factory=qtmux "
        f"location={pattern}"
    )
    pipeline = Gst.parse_launch(description)
    appsrc = pipeline.get_by_name("src")
    encoder = pipeline.get_by_name("enc")
    mux = pipeline.get_by_name("mux")
    bus = pipeline.get_bus()
    messages = []
    request_results = []
    duration = Gst.SECOND // FPS
    result = pipeline.set_state(Gst.State.PLAYING)
    if result == Gst.StateChangeReturn.FAILURE:
        raise RuntimeError("PLAYING failed")
    try:
        absolute_index = 0
        for request_index in range(3):
            # nvv4l2h264enc가 아직 첫 buffer로 negotiation되기 전에 force-IDR
            # action을 호출하면 이 JetPack 조합에서 native segfault가 난다.
            # 첫 프레임은 원래 IDR이므로 이후 요청 경계에서만 호출한다.
            if request_index > 0:
                encoder.emit("force-IDR")
            started = time.monotonic()
            for frame in make_frames(request_index)[:FRAMES]:
                payload = memoryview(frame).cast("B")
                buffer = Gst.Buffer.new_allocate(None, payload.nbytes, None)
                buffer.fill(0, payload)
                buffer.pts = absolute_index * duration
                buffer.dts = buffer.pts
                buffer.duration = duration
                flow = appsrc.emit("push-buffer", buffer)
                if flow != Gst.FlowReturn.OK:
                    raise RuntimeError(f"push failed: request={request_index}, flow={flow}")
                absolute_index += 1
            request_results.append(
                {"request": request_index, "push_elapsed_sec": time.monotonic() - started}
            )
            if request_index < 2:
                mux.emit("split-after")
            drain_messages(bus, messages)

        time.sleep(2.0)
        drain_messages(bus, messages)
        before_eos = sorted(path.name for path in output_dir.glob("fragment_*.mp4"))
        eos_started = time.monotonic()
        flow = appsrc.emit("end-of-stream")
        if flow != Gst.FlowReturn.OK:
            raise RuntimeError(f"EOS failed: {flow}")
        message = bus.timed_pop_filtered(
            15 * Gst.SECOND, Gst.MessageType.ERROR | Gst.MessageType.EOS
        )
        eos_elapsed = time.monotonic() - eos_started
        if message is None:
            raise TimeoutError("EOS timeout")
        if message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            raise RuntimeError(f"pipeline error: {error}; {debug}")
        drain_messages(bus, messages)
    finally:
        pipeline.set_state(Gst.State.NULL)
        pipeline.get_state(5 * Gst.SECOND)

    files = sorted(output_dir.glob("fragment_*.mp4"))
    report = {
        "gstreamer": Gst.version_string(),
        "requests": request_results,
        "files_visible_before_eos": before_eos,
        "eos_elapsed_sec": eos_elapsed,
        "files": [{"path": path.name, **probe(path)} for path in files],
        "messages": messages,
    }
    (output_dir / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
