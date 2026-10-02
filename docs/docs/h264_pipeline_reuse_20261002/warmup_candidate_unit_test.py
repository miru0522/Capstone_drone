"""운영 장치 없이 warmup helper의 분기와 상태기록 분리를 확인한다."""

import importlib.util
import sys
import tempfile
import types
from dataclasses import dataclass
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
CANDIDATE = HERE / "candidate_warmup"
BASE = HERE.parent / "h264_600_reapply_20260930" / "candidate"
sys.path.insert(0, str(BASE))
sys.modules.setdefault("cv2", types.ModuleType("cv2"))
sys.modules.setdefault("requests", types.ModuleType("requests"))


class FakeFrame:
    def __init__(self, shape):
        self.shape = shape


numpy_stub = types.ModuleType("numpy")
numpy_stub.uint8 = object()
numpy_stub.zeros = lambda shape, dtype=None: FakeFrame(shape)
sys.modules.setdefault("numpy", numpy_stub)

ring_buffer_stub = types.ModuleType("ring_buffer")


@dataclass
class FrameEntry:
    frame: object
    timestamp: float


ring_buffer_stub.FrameEntry = FrameEntry
ring_buffer_stub.FPS = 9
sys.modules.setdefault("ring_buffer", ring_buffer_stub)

state_store_stub = types.ModuleType("state_store")
state_store_stub.update_json = lambda *args, **kwargs: None
sys.modules.setdefault("state_store", state_store_stub)

spec = importlib.util.spec_from_file_location("warmup_candidate_uploader", CANDIDATE / "uploader.py")
uploader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uploader)


def main():
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as output:
        output.write(b"candidate")
        output_path = output.name

    captured = {}

    def fake_encode(frames, fps, *, record_state=True):
        captured["frames"] = frames
        captured["fps"] = fps
        captured["record_state"] = record_state
        return output_path

    with mock.patch.object(uploader, "CLIP_ENCODER", "h264"), mock.patch.object(
        uploader, "H264_WORKER_MODE", "persistent"
    ), mock.patch.object(uploader, "_encode_frames_h264", side_effect=fake_encode):
        assert uploader.warmup_clip_encoder(64, 48, 9) is True

    assert len(captured["frames"]) == 2
    assert captured["frames"][0].frame.shape == (48, 64, 3)
    assert captured["fps"] == 9
    assert captured["record_state"] is False
    assert not Path(output_path).exists()

    with mock.patch.object(uploader, "CLIP_ENCODER", "mp4v"), mock.patch.object(
        uploader, "_encode_frames_h264"
    ) as encode:
        assert uploader.warmup_clip_encoder(64, 48, 9) is False
        encode.assert_not_called()

    with mock.patch.object(uploader, "CLIP_ENCODER", "h264"), mock.patch.object(
        uploader, "H264_WORKER_MODE", "per_event"
    ), mock.patch.object(uploader, "_encode_frames_h264") as encode:
        assert uploader.warmup_clip_encoder(64, 48, 9) is False
        encode.assert_not_called()

    print("PASS: warmup candidate helper")


if __name__ == "__main__":
    main()
