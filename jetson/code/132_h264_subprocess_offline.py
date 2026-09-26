"""H264 부모 프로세스 경계의 성공/실패/timeout/정리 오프라인 회귀 검사."""

import os
import json
import sys
import tempfile
import textwrap
import types
from pathlib import Path

import numpy as np

CODE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE_DIR))

# 이 검사는 OpenCV 인코딩을 실행하지 않는다. 개발 PC에 cv2가 없어도 H264
# 프로세스 경계를 검증할 수 있게 import 자리만 제공한다.
try:
    import cv2  # noqa: F401
except ModuleNotFoundError:
    sys.modules["cv2"] = types.SimpleNamespace()
try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    sys.modules["requests"] = types.SimpleNamespace(RequestException=Exception)

import uploader
from ring_buffer import FrameEntry


def _write_worker(path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body), encoding="utf-8")


def _frames():
    return [
        FrameEntry(frame=np.zeros((4, 6, 3), dtype=np.uint8), timestamp=float(i))
        for i in range(3)
    ]


def _assert_no_raw_files(directory: Path) -> None:
    leftovers = list(directory.glob("anomaly_clip_*.bgr"))
    assert not leftovers, f"raw 임시파일 미정리: {leftovers}"


def main() -> None:
    original = {
        "CLIP_ENCODER": uploader.CLIP_ENCODER,
        "H264_WORKER_PATH": uploader.H264_WORKER_PATH,
        "H264_RAW_DIR": uploader.H264_RAW_DIR,
        "H264_TIMEOUT_SEC": uploader.H264_TIMEOUT_SEC,
        "H264_STATE_PATH": uploader.H264_STATE_PATH,
        "H264_WORKER_MODE": uploader.H264_WORKER_MODE,
    }
    with tempfile.TemporaryDirectory(prefix="h264_offline_") as directory_name:
        directory = Path(directory_name)
        worker = directory / "fake_worker.py"
        uploader.CLIP_ENCODER = "h264"
        uploader.H264_WORKER_PATH = str(worker)
        uploader.H264_RAW_DIR = str(directory)
        uploader.H264_STATE_PATH = str(directory / "encoder_state.json")
        uploader.H264_WORKER_MODE = "per_event"

        try:
            _write_worker(
                worker,
                """
                import pathlib, sys
                output = pathlib.Path(sys.argv[sys.argv.index('--output-partial') + 1])
                output.write_bytes(b'0000ftyp0000moov0000avc1')
                """,
            )
            result = uploader.encode_frames_to_mp4(_frames(), fps=9)
            try:
                assert Path(result).read_bytes().endswith(b"avc1")
            finally:
                os.remove(result)
            _assert_no_raw_files(directory)

            _write_worker(worker, "raise SystemExit(7)")
            try:
                uploader.encode_frames_to_mp4(_frames(), fps=9)
                raise AssertionError("worker 실패가 예외로 전달되지 않음")
            except RuntimeError as exc:
                assert "returncode=7" in str(exc)
            _assert_no_raw_files(directory)

            _write_worker(worker, "import time; time.sleep(5)")
            uploader.H264_TIMEOUT_SEC = 0.2
            try:
                uploader.encode_frames_to_mp4(_frames(), fps=9)
                raise AssertionError("timeout이 예외로 전달되지 않음")
            except TimeoutError:
                pass
            _assert_no_raw_files(directory)
            state = json.loads(Path(uploader.H264_STATE_PATH).read_text(encoding="utf-8"))
            assert state["worker_starts"] == 3
            assert state["jobs_started"] == 3
            assert state["total_successes"] == 1
            assert state["total_failures"] == 2
            assert state["consecutive_failures"] == 2
            assert state["status"] == "rollback_recommended"

            uploader.CLIP_ENCODER = "mp4v"
            mp4v_called = []
            original_mp4v = uploader._encode_frames_mp4v
            uploader._encode_frames_mp4v = lambda frames, fps: mp4v_called.append(fps) or "ok.mp4"
            try:
                assert uploader.encode_frames_to_mp4(_frames(), fps=7) == "ok.mp4"
                assert mp4v_called == [7]
            finally:
                uploader._encode_frames_mp4v = original_mp4v

            uploader.CLIP_ENCODER = "h264"
            uploader.H264_WORKER_MODE = "persistent"
            uploader.H264_TIMEOUT_SEC = 2
            _write_worker(
                worker,
                """
                import json, os, pathlib, sys
                if sys.argv[1:] != ['--serve']:
                    raise SystemExit(9)
                for line in sys.stdin:
                    request = json.loads(line)
                    pathlib.Path(request['output_partial']).write_bytes(
                        b'0000ftyp0000moov0000avc1'
                    )
                    response = pathlib.Path(request['response_path'])
                    temporary = pathlib.Path(str(response) + '.tmp')
                    temporary.write_text(json.dumps({'ok': True}), encoding='utf-8')
                    os.replace(temporary, response)
                """,
            )
            first = uploader.encode_frames_to_mp4(_frames(), fps=9)
            first_pid = uploader._persistent_worker.pid
            second = uploader.encode_frames_to_mp4(_frames(), fps=9)
            second_pid = uploader._persistent_worker.pid
            os.remove(first)
            os.remove(second)
            assert first_pid == second_pid
            _assert_no_raw_files(directory)

            uploader._stop_persistent_worker()
            _write_worker(
                worker,
                """
                import json, sys, time
                if sys.argv[1:] != ['--serve']:
                    raise SystemExit(9)
                for line in sys.stdin:
                    json.loads(line)
                    time.sleep(5)
                """,
            )
            uploader.H264_TIMEOUT_SEC = 0.2
            try:
                uploader.encode_frames_to_mp4(_frames(), fps=9)
                raise AssertionError("지속 worker timeout이 예외로 전달되지 않음")
            except TimeoutError:
                pass
            assert uploader._persistent_worker is None
            _assert_no_raw_files(directory)
        finally:
            uploader._stop_persistent_worker()
            for name, value in original.items():
                setattr(uploader, name, value)

    print("PASS: H264 per-event/persistent 성공·실패·timeout·정리 및 mp4v 선택")


if __name__ == "__main__":
    main()
