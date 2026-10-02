"""동일 합성 프레임으로 승인된 요청별 파이프라인 worker의 cold/warm 시간을 잰다."""

import json
import subprocess
import time
from pathlib import Path

from persistent_pipeline_test import BITRATE, FPS, FRAMES, HEIGHT, WIDTH, make_frames


ROOT = Path("/tmp/h264_pipeline_reuse_20261002")
WORKER = ROOT / "h264_encoder_worker.py"


def write_raw(path, frames):
    with path.open("wb") as output:
        for frame in frames:
            output.write(memoryview(frame).cast("B"))


def wait_response(path, process, timeout_sec=20.0):
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise RuntimeError(f"worker exited: returncode={process.returncode}")
        time.sleep(0.01)
    raise TimeoutError(f"response timeout: {path}")


def main():
    output_dir = ROOT / "baseline_worker_probe"
    output_dir.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        ["python3", str(WORKER), "--serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    results = []
    try:
        for index in range(3):
            raw = output_dir / f"request_{index}.bgr"
            partial = output_dir / f"request_{index}.mp4.partial"
            response = output_dir / f"request_{index}.response.json"
            for stale in (partial, response):
                stale.unlink(missing_ok=True)
            write_raw(raw, make_frames(index)[:FRAMES])
            request = {
                "input_raw": str(raw),
                "output_partial": str(partial),
                "width": WIDTH,
                "height": HEIGHT,
                "frames": FRAMES,
                "fps": FPS,
                "bitrate": BITRATE,
                "response_path": str(response),
            }
            started = time.monotonic()
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            reply = wait_response(response, process)
            results.append(
                {
                    "index": index,
                    "elapsed_sec": time.monotonic() - started,
                    "reply": reply,
                    "size_bytes": partial.stat().st_size if partial.exists() else None,
                }
            )
    finally:
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
    report = {"configuration": {"frames": FRAMES, "fps": FPS}, "results": results}
    (output_dir / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
