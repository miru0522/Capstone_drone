from pathlib import Path
import csv
import cv2
import numpy as np
import statistics
import gc
import time

from anomaly_model_trt import AnomalyPipeline

ROOT = Path("/home/hpc/ucf4_edge_videomae_compare77")
MANIFEST = ROOT / "comparison_manifest.csv"
OUT = ROOT / "comparison_vadclip77.csv"

FPS = 9.0
WINDOW = 48
THRESHOLD = 0.4073

EXCLUDE = {
    "Abuse028_x264.mp4": "OUT_OF_SCOPE_NON_HUMAN_ABUSE_SMALL_TARGET",
    "Abuse030_x264.mp4": "OUT_OF_SCOPE_NON_HUMAN_ABUSE_SMALL_TARGET",
    "Robbery050_x264.mp4": "TAXONOMY_MISMATCH_VEHICLE_THEFT_VS_VIOLENCE",
    "Robbery106_x264.mp4": "LOW_OBSERVABILITY_SMALL_WEAPON_SHORT_CUE",
    "Robbery137_x264.mp4": "LOW_OBSERVABILITY_SMALL_WEAPON_SHORT_CUE",
}

def sample_video_9fps(path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open: {path}")

    src_fps = float(cap.get(cv2.CAP_PROP_FPS))
    n_src = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if src_fps <= 0 or n_src <= 0:
        cap.release()
        raise RuntimeError(f"invalid metadata: {path}, fps={src_fps}, frames={n_src}")

    n_target = max(1, int(round(n_src * FPS / src_fps)))
    target_indices = np.round(np.arange(n_target) * src_fps / FPS).astype(int)
    target_indices = np.clip(target_indices, 0, n_src - 1)

    frames = []
    target_pos = 0
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        while target_pos < len(target_indices) and target_indices[target_pos] == frame_idx:
            frames.append(frame.copy())
            target_pos += 1

        frame_idx += 1
        if target_pos >= len(target_indices):
            break

    cap.release()

    if not frames:
        raise RuntimeError(f"no sampled frames: {path}")

    return frames

def make_window_starts(n):
    if n <= WINDOW:
        return [0]
    last = n - WINDOW
    center = last // 2
    return sorted(set([0, center, last]))

def prepare_window(frames, start):
    x = frames[start:start + WINDOW]
    if not x:
        raise RuntimeError("empty window")
    while len(x) < WINDOW:
        x.append(x[-1].copy())
    return np.stack(x, axis=0)

with MANIFEST.open("r", encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))
    fields = list(rows[0].keys())

if len(rows) != 77:
    raise RuntimeError(f"expected 77 manifest rows, got {len(rows)}")

for r in rows:
    if r["video"] in EXCLUDE:
        r["deployment_scope"] = "EXCLUDE"
        r["scope_reason"] = EXCLUDE[r["video"]]
    else:
        r["deployment_scope"] = "INCLUDE"
        r["scope_reason"] = "IN_SCOPE"

extra = [
    "deployment_scope",
    "scope_reason",
    "sampled_frames_9fps",
    "vadclip_start_score",
    "vadclip_center_score",
    "vadclip_end_score",
    "vadclip_max_score",
    "edge_center_prediction",
    "edge_any_prediction",
    "vadclip_eval_ms",
]
for c in extra:
    if c not in fields:
        fields.append(c)

print("=" * 100)
print("UCF77 VadCLIP TRT BATCH")
print("=" * 100)
print("manifest =", MANIFEST)
print("videos =", len(rows))
print("threshold =", THRESHOLD)
print("scope include =", sum(r["deployment_scope"] == "INCLUDE" for r in rows))
print("scope exclude =", sum(r["deployment_scope"] == "EXCLUDE" for r in rows))
print()

print("Loading TRT pipeline ONCE...")
pipeline = AnomalyPipeline()
print("Warmup...")
pipeline.warmup()
print("PIPELINE READY")
print()

for i, r in enumerate(rows, 1):
    clip = ROOT / "clips" / r["actual_4class"] / r["fine_category"] / r["video"]
    if not clip.exists():
        raise RuntimeError(f"missing clip: {clip}")

    t0 = time.perf_counter()
    frames = sample_video_9fps(clip)
    starts = make_window_starts(len(frames))
    scores = []

    for start in starts:
        pipeline.scorer.feature_buffer.clear()
        window = prepare_window(frames, start)
        score = float(pipeline.compute_score(window))
        scores.append((start, score))
        del window

    start_score = scores[0][1]
    end_score = scores[-1][1]

    center_target = max(0, (len(frames) - WINDOW) // 2)
    _, center_score = min(scores, key=lambda z: abs(z[0] - center_target))
    max_score = max(s for _, s in scores)

    center_pred = "Anomaly" if center_score >= THRESHOLD else "Normal"
    any_pred = "Anomaly" if max_score >= THRESHOLD else "Normal"
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    r["sampled_frames_9fps"] = str(len(frames))
    r["vadclip_start_score"] = f"{start_score:.6f}"
    r["vadclip_center_score"] = f"{center_score:.6f}"
    r["vadclip_end_score"] = f"{end_score:.6f}"
    r["vadclip_max_score"] = f"{max_score:.6f}"
    r["edge_center_prediction"] = center_pred
    r["edge_any_prediction"] = any_pred
    r["vadclip_eval_ms"] = f"{elapsed_ms:.1f}"

    print(
        f"[{i:02d}/77] "
        f"{r['fine_category']:13s} "
        f"{r['video']:28s} "
        f"center={center_score:.4f} "
        f"max={max_score:.4f} "
        f"center_pred={center_pred:7s} "
        f"scope={r['deployment_scope']}"
    )

    del frames
    gc.collect()

with OUT.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

def print_summary(title, selected):
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)

    order = [
        "Abuse", "Assault", "Fighting", "Robbery",
        "Burglary", "Stealing", "Shoplifting", "RoadAccidents"
    ]

    print(
        f"{'category':15s} {'n':>3s} {'median':>9s} {'mean':>9s} "
        f"{'center_hit':>12s} {'any_hit':>10s} {'VideoMAE9s':>12s}"
    )

    for cat in order:
        g = [r for r in selected if r["fine_category"] == cat]
        if not g:
            continue

        vals = [float(r["vadclip_center_score"]) for r in g]
        center_hit = sum(r["edge_center_prediction"] == "Anomaly" for r in g)
        any_hit = sum(r["edge_any_prediction"] == "Anomaly" for r in g)
        vm_hit = sum(
            r["videomae_same9s_pred"] == r["actual_4class"]
            for r in g
        )

        print(
            f"{cat:15s} {len(g):3d} "
            f"{statistics.median(vals):9.4f} "
            f"{statistics.mean(vals):9.4f} "
            f"{center_hit:3d}/{len(g):<3d} "
            f"{any_hit:3d}/{len(g):<3d} "
            f"{vm_hit:3d}/{len(g):<3d}"
        )

print_summary("FULL CANONICAL 77", rows)

deployment = [r for r in rows if r["deployment_scope"] == "INCLUDE"]
print_summary("DEPLOYMENT-OBSERVABLE 72", deployment)

print()
print("=" * 100)
print("EXCLUDED 5 - SCORES RETAINED FOR AUDIT")
print("=" * 100)
for r in rows:
    if r["deployment_scope"] == "EXCLUDE":
        print(
            f"{r['video']:24s} "
            f"center={float(r['vadclip_center_score']):.4f} "
            f"max={float(r['vadclip_max_score']):.4f} "
            f"VideoMAE9s={r['videomae_same9s_pred']:8s} "
            f"reason={r['scope_reason']}"
        )

print()
print("OUTPUT =", OUT)
print("STATUS=PASS")
