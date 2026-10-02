"""상시 NVENC 프로토타입의 격리 시험 harness."""

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

from persistent_h264_pipeline_prototype import Gst, PersistentH264Pipeline


WIDTH = 960
HEIGHT = 540
FPS = 9
FRAMES = 81
BITRATE = 600_000


def resource_snapshot():
    completed = subprocess.run(
        ["timeout", "2s", "tegrastats", "--interval", "1000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    line = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
    ram = re.search(r"RAM (\d+)/(\d+)MB \(lfb (\d+)x(\d+)MB\)", line)
    swap = re.search(r"SWAP (\d+)/(\d+)MB", line)
    return {
        "raw": line,
        "ram_used_mb": int(ram.group(1)) if ram else None,
        "ram_total_mb": int(ram.group(2)) if ram else None,
        "lfb_count": int(ram.group(3)) if ram else None,
        "lfb_block_mb": int(ram.group(4)) if ram else None,
        "swap_used_mb": int(swap.group(1)) if swap else None,
    }


def make_frames(pattern_id):
    colors = [
        (20, 30, 220),
        (30, 210, 40),
        (220, 40, 30),
        (30, 190, 190),
        (180, 40, 180),
    ]
    color = colors[pattern_id % len(colors)]
    frames = []
    for index in range(FRAMES):
        frame = np.full((HEIGHT, WIDTH, 3), color, dtype=np.uint8)
        x = 20 + (index * 9) % 760
        cv2.rectangle(frame, (x, 160), (x + 160, 360), (255, 255, 255), -1)
        cv2.putText(
            frame,
            f"REQUEST={pattern_id:02d} FRAME={index:02d}",
            (30, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.4,
            (0, 0, 0),
            4,
            cv2.LINE_AA,
        )
        frames.append(frame)
    return frames


def decode_summary(path, expected_frames, current_color, other_colors):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"decode open failed: {path}")
    decoded = []
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            decoded.append(frame)
    finally:
        cap.release()
    if len(decoded) != expected_frames:
        raise RuntimeError(
            f"decoded frame mismatch: path={path}, expected={expected_frames}, actual={len(decoded)}"
        )

    masks = []
    for frame in (decoded[0], decoded[-1]):
        patch = frame[400:520, 20:260].astype(np.float32)
        mean = patch.mean(axis=(0, 1))
        current_distance = float(np.linalg.norm(mean - np.asarray(current_color)))
        other_distances = [
            float(np.linalg.norm(mean - np.asarray(color))) for color in other_colors
        ]
        if other_distances and current_distance >= min(other_distances):
            raise RuntimeError(
                f"boundary contamination suspected: current={current_distance}, others={other_distances}"
            )
        masks.append(
            {
                "mean_bgr": [float(value) for value in mean],
                "current_distance": current_distance,
                "other_distances": other_distances,
            }
        )
    return {"decoded_frames": len(decoded), "boundary_patches": masks}


def run_one(encoder, output_dir, label, pattern_id, colors):
    frames = make_frames(pattern_id)
    output = output_dir / f"{label}.mp4"
    result = encoder.encode(frames, output)
    current_color = colors[pattern_id % len(colors)]
    other_colors = [color for color in colors if color != current_color]
    result["label"] = label
    result["pattern_id"] = pattern_id
    result["output"] = str(output)
    result["decode"] = decode_summary(output, FRAMES, current_color, other_colors)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sequential", type=int, default=20)
    parser.add_argument("--idle-seconds", default="1,30,300")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    colors = [
        (20, 30, 220),
        (30, 210, 40),
        (220, 40, 30),
        (30, 190, 190),
        (180, 40, 180),
    ]
    idle_seconds = [float(value) for value in args.idle_seconds.split(",") if value]
    report = {
        "started_at": time.time(),
        "configuration": {
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "frames": FRAMES,
            "bitrate": BITRATE,
            "sequential": args.sequential,
            "idle_seconds": idle_seconds,
        },
        "resources": {"before": resource_snapshot()},
        "startup": None,
        "warmup": None,
        "sequential": [],
        "idle": [],
        "error_injection": {},
        "status": "RUNNING",
    }
    encoder = PersistentH264Pipeline(WIDTH, HEIGHT, FPS, BITRATE)
    try:
        report["startup"] = encoder.start()
        report["resources"]["after_start"] = resource_snapshot()

        warm_frames = make_frames(0)[:2]
        warm_output = args.output_dir / "warmup_2frames.mp4"
        report["warmup"] = encoder.encode(warm_frames, warm_output)
        report["resources"]["after_warmup"] = resource_snapshot()

        for index in range(args.sequential):
            report["sequential"].append(
                run_one(encoder, args.output_dir, f"sequential_{index:02d}", index + 1, colors)
            )

        for index, idle in enumerate(idle_seconds):
            before = resource_snapshot()
            time.sleep(idle)
            result = run_one(
                encoder,
                args.output_dir,
                f"idle_{int(idle):03d}s",
                args.sequential + index + 1,
                colors,
            )
            report["idle"].append(
                {"idle_sec": idle, "resource_before": before, "result": result}
            )

        invalid_failed = False
        try:
            encoder.encode([np.zeros((10, 10, 3), dtype=np.uint8)], args.output_dir / "invalid.mp4")
        except Exception as exc:
            invalid_failed = True
            report["error_injection"]["invalid_input"] = {
                "rejected": True,
                "error": f"{type(exc).__name__}: {exc}",
            }
        if not invalid_failed:
            raise RuntimeError("invalid frame was not rejected")
        report["error_injection"]["after_invalid"] = run_one(
            encoder, args.output_dir, "after_invalid", 91, colors
        )

        encoder.pipeline.set_state(Gst.State.NULL)
        encoder.pipeline.get_state(5 * Gst.SECOND)
        stopped_failed = False
        try:
            encoder.encode(make_frames(92), args.output_dir / "stopped_should_fail.mp4", timeout_sec=2)
        except Exception as exc:
            stopped_failed = True
            report["error_injection"]["forced_pipeline_stop"] = {
                "detected": True,
                "error": f"{type(exc).__name__}: {exc}",
            }
        if not stopped_failed:
            raise RuntimeError("forced pipeline stop was not detected")
        report["error_injection"]["restart"] = encoder.restart()
        report["error_injection"]["after_restart"] = run_one(
            encoder, args.output_dir, "after_restart", 93, colors
        )
        report["resources"]["before_close"] = resource_snapshot()
        report["status"] = "PASS"
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        encoder.close()
        report["resources"]["after_close"] = resource_snapshot()
        report["completed_at"] = time.time()
        report["elapsed_sec"] = report["completed_at"] - report["started_at"]
        (args.output_dir / "result.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
