#!/usr/bin/env python3
"""
127_test_upload_only_960x540.py

Isolate Jetson -> hydro1 upload path WITHOUT CSI, VadCLIP, TensorRT, or hover.

1) Builds one deterministic-ish 81-frame / 9fps / 960x540 mp4v probe from an
   existing 9s review clip already on the Jetson.
2) Reuses the exact same probe file for subsequent runs.
3) POSTs it to the requested /analyze-video URL and prints status/timing/body.

Recommended:
  # through nginx/frontend
  python3 -u 127_test_upload_only_960x540.py \
    --url http://203.249.90.3:8031/analyze-video

  # only if 8031 fails again: bypass nginx, same exact file
  python3 -u 127_test_upload_only_960x540.py \
    --url http://203.249.90.3:8000/analyze-video
"""

import argparse
import hashlib
import os
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import requests

DEFAULT_OUT = Path("/tmp/v6_upload_probe_81f_9fps_960x540_mp4v.mp4")
SEARCH_ROOTS = [
    Path("/home/hpc/aihub_diag90_edge_videomae_compare"),
    Path("/home/hpc/ucf4_edge_videomae_compare77"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_source():
    for root in SEARCH_ROOTS:
        if root.exists():
            files = sorted(root.rglob("*.mp4"))
            if files:
                return files[0]
    return None


def make_probe(src: Path, out: Path):
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open source: {src}")

    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n <= 0:
        cap.release()
        raise RuntimeError(f"invalid frame count for source: {src}")

    indices = np.linspace(0, n - 1, 81).round().astype(int)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out), fourcc, 9, (960, 540))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError("VideoWriter mp4v open failed")

    wrote = 0
    try:
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"read failed at source frame {idx}")
            frame = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA)
            writer.write(frame)
            wrote += 1
    finally:
        writer.release()
        cap.release()

    if wrote != 81 or not out.exists() or out.stat().st_size <= 0:
        raise RuntimeError(
            f"probe build failed: wrote={wrote}, exists={out.exists()}, "
            f"size={out.stat().st_size if out.exists() else -1}"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--url",
        default="http://203.249.90.3:8031/analyze-video",
        help="Target analyze-video URL",
    )
    ap.add_argument("--source", default=None)
    ap.add_argument("--probe", default=str(DEFAULT_OUT))
    ap.add_argument("--timeout", type=float, default=190.0)
    args = ap.parse_args()

    probe = Path(args.probe)

    if not probe.exists():
        src = Path(args.source) if args.source else find_source()
        if src is None or not src.exists():
            raise SystemExit(
                "ERROR: no source mp4 found. Use --source /path/to/video.mp4"
            )
        print("SOURCE =", src, flush=True)
        print("Building exact reusable upload probe...", flush=True)
        t0 = time.time()
        make_probe(src, probe)
        print(f"PROBE_BUILD_SEC = {time.time()-t0:.3f}", flush=True)
    else:
        print("Reusing existing probe.", flush=True)

    print("PROBE =", probe, flush=True)
    print("PROBE_SIZE_BYTES =", probe.stat().st_size, flush=True)
    print("PROBE_SHA256 =", sha256(probe), flush=True)
    print("TARGET_URL =", args.url, flush=True)

    t0 = time.time()
    try:
        with probe.open("rb") as f:
            files = {"video": (probe.name, f, "video/mp4")}
            r = requests.post(args.url, files=files, timeout=args.timeout)
        elapsed = time.time() - t0

        print("POST_ELAPSED_SEC =", round(elapsed, 3), flush=True)
        print("HTTP_STATUS =", r.status_code, flush=True)
        print("RESPONSE_LEN =", len(r.content), flush=True)
        print("RESPONSE_HEAD =", r.text[:1000], flush=True)

        if r.status_code == 200:
            print("STATUS=PASS", flush=True)
            return 0

        print("STATUS=HTTP_FAIL", flush=True)
        return 2

    except Exception as e:
        elapsed = time.time() - t0
        print("POST_ELAPSED_SEC =", round(elapsed, 3), flush=True)
        print("EXCEPTION =", repr(e), flush=True)
        print("STATUS=TRANSPORT_FAIL", flush=True)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
