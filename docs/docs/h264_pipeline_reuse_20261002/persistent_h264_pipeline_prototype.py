"""Jetson용 상시 NVENC + 요청별 MP4 mux 프로토타입.

운영 코드와 독립된 검증용이다. nvv4l2h264enc까지의 파이프라인은 계속 PLAYING
상태로 유지하고, 요청마다 H.264 access unit을 appsink에서 정확히 수집한 뒤
가벼운 qtmux 파이프라인만 새로 생성한다.
"""

import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst


Gst.init(None)


class PipelineError(RuntimeError):
    pass


class PersistentH264Pipeline:
    def __init__(self, width=960, height=540, fps=9, bitrate=600_000):
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)
        self.bitrate = int(bitrate)
        self.frame_bytes = self.width * self.height * 3
        self.frame_duration = Gst.SECOND // self.fps
        self.pipeline = None
        self.appsrc = None
        self.encoder = None
        self.appsink = None
        self.bus = None
        self.next_pts = 0
        self.request_sequence = 0
        self.requests_since_start = 0
        self.lock = threading.Lock()

    def _description(self):
        return (
            "appsrc name=src is-live=false block=false max-bytes=0 "
            "format=time do-timestamp=false "
            f"caps=video/x-raw,format=BGR,width={self.width},height={self.height},"
            f"framerate={self.fps}/1 "
            "! videoconvert ! video/x-raw,format=NV12 "
            "! nvvidconv ! video/x-raw(memory:NVMM),format=NV12 "
            f"! nvv4l2h264enc name=enc bitrate={self.bitrate} "
            "insert-sps-pps=true iframeinterval=256 idrinterval=256 "
            "! h264parse config-interval=-1 "
            "! video/x-h264,stream-format=byte-stream,alignment=au "
            "! appsink name=encoded emit-signals=false sync=false "
            "max-buffers=256 drop=false"
        )

    def _raise_bus_error(self):
        if self.bus is None:
            return
        message = self.bus.pop_filtered(Gst.MessageType.ERROR)
        if message is None:
            return
        error, debug = message.parse_error()
        raise PipelineError(f"GStreamer error: {error}; debug={debug}")

    def start(self, timeout_sec=0.25):
        if self.pipeline is not None:
            raise PipelineError("pipeline already started")
        started = time.monotonic()
        pipeline = Gst.parse_launch(self._description())
        appsrc = pipeline.get_by_name("src")
        encoder = pipeline.get_by_name("enc")
        appsink = pipeline.get_by_name("encoded")
        if appsrc is None or encoder is None or appsink is None:
            pipeline.set_state(Gst.State.NULL)
            raise PipelineError("required element lookup failed")

        result = pipeline.set_state(Gst.State.PLAYING)
        if result == Gst.StateChangeReturn.FAILURE:
            pipeline.set_state(Gst.State.NULL)
            raise PipelineError("PLAYING state request failed")
        # 입력이 없는 appsrc 파이프라인은 PAUSED→PLAYING 전환을 완료하지 않을 수
        # 있다. 여기서 ASYNC_DONE을 기다리지 않고 첫 더미 요청의 실제 출력으로
        # negotiation과 NVENC 동작을 증명한다.
        state_result, current, pending = pipeline.get_state(int(timeout_sec * Gst.SECOND))
        if state_result == Gst.StateChangeReturn.FAILURE:
            pipeline.set_state(Gst.State.NULL)
            raise PipelineError(f"PLAYING transition failed: current={current}, pending={pending}")

        self.pipeline = pipeline
        self.appsrc = appsrc
        self.encoder = encoder
        self.appsink = appsink
        self.bus = pipeline.get_bus()
        self.requests_since_start = 0
        self._raise_bus_error()
        return {
            "elapsed_sec": time.monotonic() - started,
            "state_result": int(state_result),
            "current_state": int(current),
            "pending_state": int(pending),
        }

    def close(self):
        pipeline = self.pipeline
        self.pipeline = None
        self.appsrc = None
        self.encoder = None
        self.appsink = None
        self.bus = None
        if pipeline is not None:
            pipeline.set_state(Gst.State.NULL)
            pipeline.get_state(5 * Gst.SECOND)

    def restart(self):
        self.close()
        self.next_pts = 0
        return self.start()

    def _push_frames(self, frames):
        first_pts = self.next_pts
        # 첫 buffer negotiation 전 force-IDR은 이 JetPack 조합에서 native
        # segfault를 낼 수 있다. 새 pipeline의 첫 프레임은 원래 IDR이다.
        if self.requests_since_start > 1:
            self.encoder.emit("force-IDR")
        for index, frame in enumerate(frames):
            payload = memoryview(frame).cast("B")
            if payload.nbytes != self.frame_bytes:
                raise ValueError(
                    f"frame size mismatch: index={index}, expected={self.frame_bytes}, "
                    f"actual={payload.nbytes}"
                )
            buffer = Gst.Buffer.new_allocate(None, self.frame_bytes, None)
            buffer.fill(0, payload)
            buffer.pts = first_pts + index * self.frame_duration
            buffer.dts = buffer.pts
            buffer.duration = self.frame_duration
            flow = self.appsrc.emit("push-buffer", buffer)
            if flow != Gst.FlowReturn.OK:
                raise PipelineError(f"push-buffer failed: index={index}, flow={flow}")
        self.next_pts += len(frames) * self.frame_duration
        return first_pts

    def _pull_access_units(self, expected_frames, first_pts, timeout_sec):
        deadline = time.monotonic() + timeout_sec
        units = []
        while len(units) < expected_frames:
            self._raise_bus_error()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"encoded AU timeout: expected={expected_frames}, actual={len(units)}"
                )
            sample = self.appsink.emit(
                "try-pull-sample", int(min(remaining, 0.25) * Gst.SECOND)
            )
            if sample is None:
                continue
            buffer = sample.get_buffer()
            ok, mapped = buffer.map(Gst.MapFlags.READ)
            if not ok:
                raise PipelineError("encoded buffer map failed")
            try:
                payload = bytes(mapped.data)
            finally:
                buffer.unmap(mapped)
            if not payload:
                raise PipelineError("empty encoded AU")
            units.append(
                {
                    "payload": payload,
                    "pts": int(buffer.pts - first_pts),
                    "duration": int(buffer.duration),
                    "flags": int(buffer.get_flags()),
                }
            )
        return units

    def _mux_mp4(self, units, output_path, timeout_sec):
        partial_path = str(output_path) + ".partial"
        for path in (str(output_path), partial_path):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

        description = (
            "appsrc name=src block=true format=time "
            f"caps=video/x-h264,stream-format=byte-stream,alignment=au,"
            f"framerate={self.fps}/1 "
            "! h264parse config-interval=-1 "
            "! video/x-h264,stream-format=avc,alignment=au "
            "! qtmux ! filesink name=sink"
        )
        pipeline = Gst.parse_launch(description)
        appsrc = pipeline.get_by_name("src")
        sink = pipeline.get_by_name("sink")
        sink.set_property("location", partial_path)
        result = pipeline.set_state(Gst.State.PLAYING)
        if result == Gst.StateChangeReturn.FAILURE:
            pipeline.set_state(Gst.State.NULL)
            raise PipelineError("mux pipeline PLAYING failed")

        try:
            for index, unit in enumerate(units):
                payload = unit["payload"]
                buffer = Gst.Buffer.new_allocate(None, len(payload), None)
                buffer.fill(0, payload)
                buffer.pts = index * self.frame_duration
                buffer.dts = buffer.pts
                buffer.duration = self.frame_duration
                flow = appsrc.emit("push-buffer", buffer)
                if flow != Gst.FlowReturn.OK:
                    raise PipelineError(f"mux push failed: index={index}, flow={flow}")
            flow = appsrc.emit("end-of-stream")
            if flow != Gst.FlowReturn.OK:
                raise PipelineError(f"mux EOS failed: flow={flow}")
            bus = pipeline.get_bus()
            message = bus.timed_pop_filtered(
                int(timeout_sec * Gst.SECOND),
                Gst.MessageType.ERROR | Gst.MessageType.EOS,
            )
            if message is None:
                raise TimeoutError("mux EOS timeout")
            if message.type == Gst.MessageType.ERROR:
                error, debug = message.parse_error()
                raise PipelineError(f"mux error: {error}; debug={debug}")
        finally:
            pipeline.set_state(Gst.State.NULL)
            pipeline.get_state(5 * Gst.SECOND)

        if not os.path.isfile(partial_path) or os.path.getsize(partial_path) <= 0:
            raise PipelineError("mux output missing or empty")
        os.replace(partial_path, output_path)

    @staticmethod
    def probe(path):
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
                str(path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return json.loads(completed.stdout)

    def encode(self, frames, output_path, timeout_sec=15.0):
        if not frames:
            raise ValueError("frames must not be empty")
        output_path = Path(output_path)
        with self.lock:
            if self.pipeline is None:
                raise PipelineError("pipeline not started")
            for index, frame in enumerate(frames):
                payload = memoryview(frame).cast("B")
                if payload.nbytes != self.frame_bytes:
                    raise ValueError(
                        f"frame size mismatch: index={index}, expected={self.frame_bytes}, "
                        f"actual={payload.nbytes}"
                    )
            state_result, current, pending = self.pipeline.get_state(0)
            if state_result == Gst.StateChangeReturn.FAILURE or current == Gst.State.NULL:
                raise PipelineError(
                    f"pipeline is not usable: current={current}, pending={pending}"
                )
            if self.requests_since_start > 0 and current != Gst.State.PLAYING:
                raise PipelineError(
                    f"pipeline left PLAYING: current={current}, pending={pending}"
                )
            self.request_sequence += 1
            self.requests_since_start += 1
            total_started = time.monotonic()
            encode_started = time.monotonic()
            first_pts = self.next_pts
            # Jetson의 nvv4l2h264enc는 downstream appsink를 동시에 비우지 않으면
            # appsrc.push-buffer에 프레임 주기만큼 backpressure를 건다. 한 요청의
            # AU를 별도 drain thread에서 수집해 encoder pipeline은 계속 흐르게 한다.
            pull_started = time.monotonic()
            with ThreadPoolExecutor(max_workers=1) as executor:
                pull_future = executor.submit(
                    self._pull_access_units,
                    len(frames),
                    first_pts,
                    timeout_sec,
                )
                pushed_first_pts = self._push_frames(frames)
                push_elapsed = time.monotonic() - encode_started
                if pushed_first_pts != first_pts:
                    raise PipelineError(
                        f"request PTS race: expected={first_pts}, actual={pushed_first_pts}"
                    )
                units = pull_future.result(timeout=timeout_sec + 1.0)
            pull_elapsed = time.monotonic() - pull_started
            encode_elapsed = time.monotonic() - encode_started

            mux_started = time.monotonic()
            self._mux_mp4(units, output_path, timeout_sec)
            mux_elapsed = time.monotonic() - mux_started
            probe = self.probe(output_path)
            return {
                "request_sequence": self.request_sequence,
                "encoded_au_count": len(units),
                "first_au_pts": units[0]["pts"],
                "last_au_pts": units[-1]["pts"],
                "first_au_flags": units[0]["flags"],
                "push_elapsed_sec": push_elapsed,
                "pull_elapsed_sec": pull_elapsed,
                "encode_elapsed_sec": encode_elapsed,
                "mux_elapsed_sec": mux_elapsed,
                "total_elapsed_sec": time.monotonic() - total_started,
                "size_bytes": output_path.stat().st_size,
                "probe": probe,
            }


def load_raw_bgr(path, width, height, count):
    frame_bytes = width * height * 3
    payload = Path(path).read_bytes()
    expected = frame_bytes * count
    if len(payload) != expected:
        raise ValueError(f"raw size mismatch: expected={expected}, actual={len(payload)}")
    return [
        payload[index * frame_bytes : (index + 1) * frame_bytes]
        for index in range(count)
    ]
