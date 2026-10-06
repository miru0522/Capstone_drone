"""NVENC를 열지 않는 H264 worker 준비 경로의 회귀 시험."""

import importlib.util
import io
import json
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
CANDIDATE = HERE / "candidate_preload_only"
BASE = HERE.parent / "h264_600_reapply_20260930" / "candidate"
sys.path.insert(0, str(BASE))
sys.modules.setdefault("cv2", types.ModuleType("cv2"))
sys.modules.setdefault("requests", types.ModuleType("requests"))

ring_buffer_stub = types.ModuleType("ring_buffer")
ring_buffer_stub.FrameEntry = object
ring_buffer_stub.FPS = 9
sys.modules.setdefault("ring_buffer", ring_buffer_stub)

state_store_stub = types.ModuleType("state_store")
state_store_stub.update_json = lambda *args, **kwargs: None
sys.modules.setdefault("state_store", state_store_stub)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


uploader = load_module("preload_only_uploader", CANDIDATE / "uploader.py")
worker = load_module("preload_only_worker", CANDIDATE / "h264_encoder_worker.py")


def test_uploader_prepare_request() -> None:
    captured = {}
    fake_process = types.SimpleNamespace(pid=4321)
    response_path = str(HERE / "fake_prepare.response.json")

    def fake_run(request, response_path, deadline, *, record_state=True):
        captured.update(
            request=request,
            response_path=response_path,
            deadline=deadline,
            record_state=record_state,
        )
        return fake_process

    with mock.patch.object(
        uploader, "CLIP_ENCODER", "h264"
    ), mock.patch.object(uploader, "H264_WORKER_MODE", "persistent"), mock.patch.object(
        uploader.tempfile, "mkstemp", return_value=(99, response_path)
    ), mock.patch.object(uploader.os, "close") as close_fd, mock.patch.object(
        uploader.os, "remove"
    ), mock.patch.object(uploader, "_run_persistent_worker", side_effect=fake_run):
        assert uploader.prepare_clip_encoder() is True

    assert captured["request"] == {"action": "prepare"}
    assert captured["record_state"] is False
    assert captured["response_path"] == response_path
    close_fd.assert_called_once_with(99)


def test_prepare_skips_other_modes() -> None:
    with mock.patch.object(uploader, "CLIP_ENCODER", "mp4v"), mock.patch.object(
        uploader, "_run_persistent_worker"
    ) as run:
        assert uploader.prepare_clip_encoder() is False
        run.assert_not_called()

    with mock.patch.object(uploader, "CLIP_ENCODER", "h264"), mock.patch.object(
        uploader, "H264_WORKER_MODE", "per_event"
    ), mock.patch.object(uploader, "_run_persistent_worker") as run:
        assert uploader.prepare_clip_encoder() is False
        run.assert_not_called()


def test_worker_prepare_protocol() -> None:
    calls = []
    responses = []
    response_path = "/tmp/prepare.response.json"
    request = json.dumps({"action": "prepare", "response_path": response_path})
    with mock.patch.object(
        worker, "_get_gstreamer", side_effect=lambda: calls.append(True)
    ), mock.patch.object(
        worker, "_write_response", side_effect=lambda path, value: responses.append((path, value))
    ), mock.patch.object(sys, "stdin", io.StringIO(request + "\n")):
        assert worker.serve() == 0

    assert responses == [(response_path, {"ok": True, "prepared": "gstreamer"})]
    assert calls == [True]


def main() -> None:
    test_uploader_prepare_request()
    test_prepare_skips_other_modes()
    test_worker_prepare_protocol()
    print("PASS: preload-only candidate")


if __name__ == "__main__":
    main()
