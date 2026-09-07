#!/usr/bin/env python3
from pathlib import Path
import csv
import cv2
import numpy as np
import gc
import json
import time
import torch

ROOT = Path("/home/hpc/aihub_diag90_edge_videomae_compare")
RESULT119 = ROOT / "comparison_aihub90_vadclip.csv"
OUTCSV = ROOT / "parity_120_real_aihub_pairs.csv"
OUTJSON = ROOT / "parity_120_real_aihub_pairs_summary.json"

CODE_DIR = Path("/home/hpc/drone_2026/code")
FPS = 9.0
WINDOW = 48
THRESHOLD = 0.4073

# 대표 failure / false-positive에서 5개 pair를 선택.
ANCHORS = [
    "fight_29-1_cam01_positive",
    "burglary_76-3_cam01_positive",
    "assault_406-4_cam01_positive",
    "fight_15-4_cam01_normal",
    "assault_18-3_cam01_normal",
]

MAX_PT_TRT_ABS_DELTA = 0.01
MAX_TRT_REPLAY_ABS_DELTA = 0.001


def boolish(x):
    return str(x).strip().lower() in ("true", "1", "yes")


def sample_video_9fps(path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open: {path}")

    src_fps = float(cap.get(cv2.CAP_PROP_FPS))
    n_src = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if src_fps <= 0 or n_src <= 0:
        cap.release()
        raise RuntimeError(
            f"invalid metadata: {path}, fps={src_fps}, frames={n_src}"
        )

    n_target = max(1, int(round(n_src * FPS / src_fps)))
    target_indices = np.round(
        np.arange(n_target) * src_fps / FPS
    ).astype(int)
    target_indices = np.clip(target_indices, 0, n_src - 1)

    frames = []
    target_pos = 0
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        while (
            target_pos < len(target_indices)
            and target_indices[target_pos] == frame_idx
        ):
            frames.append(frame.copy())
            target_pos += 1

        frame_idx += 1
        if target_pos >= len(target_indices):
            break

    cap.release()
    if not frames:
        raise RuntimeError(f"no frames sampled: {path}")
    return frames


def window_starts(n):
    if n <= WINDOW:
        return [0]
    last = n - WINDOW
    return sorted(set([0, last // 2, last]))


def prepare_window(frames, start):
    x = frames[start:start + WINDOW]
    if not x:
        raise RuntimeError("empty window")
    while len(x) < WINDOW:
        x.append(x[-1].copy())
    return np.stack(x, axis=0)


def score_clip(pipeline, clip_path):
    frames = sample_video_9fps(clip_path)
    starts = window_starts(len(frames))
    vals = []

    for st in starts:
        if hasattr(pipeline, "scorer") and hasattr(pipeline.scorer, "feature_buffer"):
            pipeline.scorer.feature_buffer.clear()
        win = prepare_window(frames, st)
        score = float(pipeline.compute_score(win))
        vals.append((st, score))
        del win

    center_target = max(0, (len(frames) - WINDOW) // 2)
    _, center = min(vals, key=lambda z: abs(z[0] - center_target))
    start = vals[0][1]
    end = vals[-1][1]
    mx = max(s for _, s in vals)

    del frames
    gc.collect()

    return {
        "start": start,
        "center": center,
        "end": end,
        "max": mx,
    }


def locate_clip(row):
    p = ROOT / "clips" / row["actual_4class"] / row["fine_category"] / row["clip_kind"] / row["video"]
    if not p.exists():
        raise RuntimeError(f"missing clip: {p}")
    return p


if not RESULT119.exists():
    raise SystemExit(f"ERROR: missing 119 result: {RESULT119}")

with RESULT119.open("r", encoding="utf-8-sig", newline="") as f:
    all_rows = list(csv.DictReader(f))

if len(all_rows) != 90:
    raise SystemExit(f"ERROR: expected 90 rows, got {len(all_rows)}")

# Anchor + same pair_key counterpart.
selected = {}
for anchor in ANCHORS:
    matches = [r for r in all_rows if anchor in r["video"]]
    if len(matches) != 1:
        raise SystemExit(f"ERROR: anchor {anchor!r} matched {len(matches)} rows")
    a = matches[0]
    pair = [r for r in all_rows if r["pair_key"] == a["pair_key"]]
    if len(pair) != 2:
        raise SystemExit(
            f"ERROR: pair_key {a['pair_key']} expected 2 rows, got {len(pair)}"
        )
    for r in pair:
        selected[r["video"]] = r

rows = list(selected.values())
rows.sort(key=lambda r: (r["fine_category"], r["pair_key"], r["clip_kind"]))

print("=" * 110)
print("120 REAL AIHUB PAIR · PYTORCH vs TENSORRT SCORE PARITY")
print("=" * 110)
print("selected clips =", len(rows))
for r in rows:
    print(
        r["fine_category"],
        r["clip_kind"],
        r["video"],
        "119_center=", r["vadclip_center_score"],
        "119_max=", r["vadclip_max_score"],
    )

# -------------------------------------------------------------------------
# Phase A: PyTorch runtime
# -------------------------------------------------------------------------
print("\n===== PHASE A · PYTORCH RUNTIME =====")
import anomaly_model as anomaly_pt

pt = anomaly_pt.AnomalyPipeline()
if hasattr(pt, "warmup"):
    pt.warmup()

pt_scores = {}
for i, r in enumerate(rows, 1):
    p = locate_clip(r)
    t0 = time.perf_counter()
    s = score_clip(pt, p)
    ms = (time.perf_counter() - t0) * 1000
    pt_scores[r["video"]] = s
    print(
        f"[PT {i:02d}/{len(rows)}] {r['video']} "
        f"center={s['center']:.6f} max={s['max']:.6f} {ms:.1f}ms",
        flush=True,
    )

del pt
gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()
    torch.cuda.synchronize()
print("PyTorch pipeline released.", flush=True)

# -------------------------------------------------------------------------
# Phase B: TensorRT runtime
# -------------------------------------------------------------------------
print("\n===== PHASE B · TENSORRT RUNTIME =====")
import anomaly_model_trt as anomaly_trt

trt = anomaly_trt.AnomalyPipeline()
if hasattr(trt, "warmup"):
    trt.warmup()

trt_scores = {}
for i, r in enumerate(rows, 1):
    p = locate_clip(r)
    t0 = time.perf_counter()
    s = score_clip(trt, p)
    ms = (time.perf_counter() - t0) * 1000
    trt_scores[r["video"]] = s
    print(
        f"[TRT {i:02d}/{len(rows)}] {r['video']} "
        f"center={s['center']:.6f} max={s['max']:.6f} {ms:.1f}ms",
        flush=True,
    )

# -------------------------------------------------------------------------
# Compare
# -------------------------------------------------------------------------
print("\n===== PARITY TABLE =====")
out = []
overall_pass = True

for r in rows:
    name = r["video"]
    ps = pt_scores[name]
    ts = trt_scores[name]
    old_center = float(r["vadclip_center_score"])
    old_max = float(r["vadclip_max_score"])

    d_center = abs(ps["center"] - ts["center"])
    d_max = abs(ps["max"] - ts["max"])
    replay_center = abs(ts["center"] - old_center)
    replay_max = abs(ts["max"] - old_max)

    pt_pred = "Anomaly" if ps["center"] >= THRESHOLD else "Normal"
    trt_pred = "Anomaly" if ts["center"] >= THRESHOLD else "Normal"

    passed = (
        d_center <= MAX_PT_TRT_ABS_DELTA
        and d_max <= MAX_PT_TRT_ABS_DELTA
        and replay_center <= MAX_TRT_REPLAY_ABS_DELTA
        and replay_max <= MAX_TRT_REPLAY_ABS_DELTA
        and pt_pred == trt_pred
    )
    overall_pass &= passed

    row = {
        "fine_category": r["fine_category"],
        "clip_kind": r["clip_kind"],
        "actual_4class": r["actual_4class"],
        "video": name,
        "pair_key": r["pair_key"],
        "pt_center": ps["center"],
        "trt_center": ts["center"],
        "abs_delta_center": d_center,
        "pt_max": ps["max"],
        "trt_max": ts["max"],
        "abs_delta_max": d_max,
        "trt119_center": old_center,
        "trt_replay_delta_center": replay_center,
        "trt119_max": old_max,
        "trt_replay_delta_max": replay_max,
        "pt_center_pred": pt_pred,
        "trt_center_pred": trt_pred,
        "parity_pass": passed,
        "review_clip_path": str(locate_clip(r)),
    }
    out.append(row)

    print(
        f"{r['fine_category']:9s} {r['clip_kind']:8s} "
        f"PT={ps['center']:.6f} TRT={ts['center']:.6f} "
        f"|Δ|={d_center:.6f} "
        f"TRT-vs-119={replay_center:.6f} "
        f"pred={pt_pred}/{trt_pred} PASS={passed}"
    )

fields = list(out[0].keys())
with OUTCSV.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(out)

summary = {
    "selected_clips": len(out),
    "max_pt_trt_abs_delta_center": max(x["abs_delta_center"] for x in out),
    "max_pt_trt_abs_delta_max": max(x["abs_delta_max"] for x in out),
    "max_trt_replay_delta_center": max(x["trt_replay_delta_center"] for x in out),
    "max_trt_replay_delta_max": max(x["trt_replay_delta_max"] for x in out),
    "all_center_predictions_match": all(
        x["pt_center_pred"] == x["trt_center_pred"] for x in out
    ),
    "overall_pass": bool(overall_pass),
    "threshold": THRESHOLD,
    "pt_trt_abs_delta_gate": MAX_PT_TRT_ABS_DELTA,
    "trt_replay_abs_delta_gate": MAX_TRT_REPLAY_ABS_DELTA,
    "out_csv": str(OUTCSV),
}

OUTJSON.write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print("\n===== SUMMARY =====")
for k, v in summary.items():
    print(k, "=", v)

print("STATUS=" + ("PASS" if overall_pass else "REVIEW"))
