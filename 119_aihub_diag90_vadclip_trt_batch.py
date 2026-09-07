#!/usr/bin/env python3
from pathlib import Path
import csv
import cv2
import numpy as np
import statistics
import time
import gc

from anomaly_model_trt import AnomalyPipeline

ROOT = Path("/home/hpc/aihub_diag90_edge_videomae_compare")
MANIFEST = ROOT / "comparison_manifest_aihub90.csv"
OUT = ROOT / "comparison_aihub90_vadclip.csv"

FPS = 9.0
WINDOW = 48
THRESHOLD = 0.4073


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
        raise RuntimeError(f"no sampled frames: {path}")

    return frames, src_fps, n_src


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


def edge_expected(actual):
    return "Normal" if actual == "Normal" else "Anomaly"


def edge_correct(pred, actual):
    return pred == edge_expected(actual)


def system_case(edge_ok, vm_ok):
    if edge_ok and vm_ok:
        return "BOTH_OK"
    if (not edge_ok) and vm_ok:
        return "EDGE_ONLY_FAIL"
    if edge_ok and (not vm_ok):
        return "VIDEOMAE_ONLY_FAIL"
    return "BOTH_FAIL"


def binary_auc(scores, labels):
    # labels: 1=positive anomaly, 0=Normal
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int64)
    n_pos = int(labels.sum())
    n_neg = int(len(labels) - n_pos)
    if n_pos == 0 or n_neg == 0:
        return float("nan")

    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    ranks = np.zeros(len(scores), dtype=np.float64)

    i = 0
    while i < len(scores):
        j = i + 1
        while j < len(scores) and sorted_scores[j] == sorted_scores[i]:
            j += 1
        # ranks are 1-based; tied samples receive average rank
        avg_rank = ((i + 1) + j) / 2.0
        ranks[order[i:j]] = avg_rank
        i = j

    sum_pos = float(ranks[labels == 1].sum())
    return (
        sum_pos - n_pos * (n_pos + 1) / 2.0
    ) / (n_pos * n_neg)


def fmt_rate(hit, n):
    return f"{hit}/{n} ({100.0*hit/n:.1f}%)" if n else "NA"


with MANIFEST.open("r", encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))
    fields = list(rows[0].keys())

if len(rows) != 90:
    raise RuntimeError(f"expected 90 rows, got {len(rows)}")

extra = [
    "sampled_frames_9fps",
    "source_fps",
    "source_frames",
    "vadclip_start_score",
    "vadclip_center_score",
    "vadclip_end_score",
    "vadclip_max_score",
    "edge_center_prediction",
    "edge_any_prediction",
    "edge_center_correct",
    "edge_any_correct",
    "system_case_center",
    "system_case_any",
    "vadclip_eval_ms",
]
for c in extra:
    if c not in fields:
        fields.append(c)

print("=" * 110)
print("AIHUB DIAGNOSTIC90 VadCLIP TRT PAIRED EVALUATION")
print("=" * 110)
print("manifest =", MANIFEST)
print("videos =", len(rows))
print("threshold =", THRESHOLD)
print("NOTE: threshold is frozen UCF temporary threshold; no AIHub retuning.")
print()

print("Loading TRT pipeline ONCE...")
pipeline = AnomalyPipeline()
print("Warmup...")
pipeline.warmup()
print("PIPELINE READY")
print()

for i, r in enumerate(rows, 1):
    clip = (
        ROOT
        / "clips"
        / r["actual_4class"]
        / r["fine_category"]
        / r["clip_kind"]
        / r["video"]
    )
    if not clip.exists():
        raise RuntimeError(f"missing clip: {clip}")

    t0 = time.perf_counter()
    frames, src_fps, n_src = sample_video_9fps(clip)
    starts = make_window_starts(len(frames))
    scores = []

    for start in starts:
        # Independent diagnostic windows; reset temporal feature buffer.
        pipeline.scorer.feature_buffer.clear()
        window = prepare_window(frames, start)
        score = float(pipeline.compute_score(window))
        scores.append((start, score))
        del window

    start_score = scores[0][1]
    end_score = scores[-1][1]
    center_target = max(0, (len(frames) - WINDOW) // 2)
    _, center_score = min(
        scores, key=lambda z: abs(z[0] - center_target)
    )
    max_score = max(s for _, s in scores)

    center_pred = "Anomaly" if center_score >= THRESHOLD else "Normal"
    any_pred = "Anomaly" if max_score >= THRESHOLD else "Normal"

    center_ok = edge_correct(center_pred, r["actual_4class"])
    any_ok = edge_correct(any_pred, r["actual_4class"])
    vm_ok = str(r["videomae_correct"]).strip().lower() in ("true", "1")

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    r["sampled_frames_9fps"] = str(len(frames))
    r["source_fps"] = f"{src_fps:.6f}"
    r["source_frames"] = str(n_src)
    r["vadclip_start_score"] = f"{start_score:.6f}"
    r["vadclip_center_score"] = f"{center_score:.6f}"
    r["vadclip_end_score"] = f"{end_score:.6f}"
    r["vadclip_max_score"] = f"{max_score:.6f}"
    r["edge_center_prediction"] = center_pred
    r["edge_any_prediction"] = any_pred
    r["edge_center_correct"] = str(center_ok)
    r["edge_any_correct"] = str(any_ok)
    r["system_case_center"] = system_case(center_ok, vm_ok)
    r["system_case_any"] = system_case(any_ok, vm_ok)
    r["vadclip_eval_ms"] = f"{elapsed_ms:.1f}"

    print(
        f"[{i:02d}/90] "
        f"{r['fine_category']:9s} "
        f"{r['clip_kind']:8s} "
        f"actual={r['actual_4class']:8s} "
        f"center={center_score:.4f} "
        f"max={max_score:.4f} "
        f"edge={center_pred:7s} "
        f"edge_ok={str(center_ok):5s} "
        f"vm={r['videomae_prediction']:8s}"
    )

    del frames
    gc.collect()

with OUT.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

# ---------- Overall metrics ----------
pos = [r for r in rows if r["actual_4class"] != "Normal"]
neg = [r for r in rows if r["actual_4class"] == "Normal"]

pos_center_hit = sum(r["edge_center_prediction"] == "Anomaly" for r in pos)
pos_any_hit = sum(r["edge_any_prediction"] == "Anomaly" for r in pos)
neg_center_ok = sum(r["edge_center_prediction"] == "Normal" for r in neg)
neg_any_ok = sum(r["edge_any_prediction"] == "Normal" for r in neg)

center_recall = pos_center_hit / len(pos)
any_recall = pos_any_hit / len(pos)
center_spec = neg_center_ok / len(neg)
any_spec = neg_any_ok / len(neg)

center_scores = [float(r["vadclip_center_score"]) for r in rows]
max_scores = [float(r["vadclip_max_score"]) for r in rows]
labels = [0 if r["actual_4class"] == "Normal" else 1 for r in rows]

center_auc = binary_auc(center_scores, labels)
max_auc = binary_auc(max_scores, labels)

vm_correct = sum(
    str(r["videomae_correct"]).strip().lower() in ("true", "1")
    for r in rows
)

print()
print("=" * 110)
print("OVERALL EDGE METRICS")
print("=" * 110)
print("Positive anomaly clips =", len(pos))
print("Normal clips           =", len(neg))
print("CENTER positive recall =", fmt_rate(pos_center_hit, len(pos)))
print("CENTER specificity     =", fmt_rate(neg_center_ok, len(neg)))
print(f"CENTER FPR             = {100.0*(1-center_spec):.1f}%")
print(f"CENTER balanced acc    = {100.0*(center_recall+center_spec)/2.0:.1f}%")
print(f"CENTER ROC-AUC         = {center_auc:.4f}")
print()
print("ANY/MAX positive recall=", fmt_rate(pos_any_hit, len(pos)))
print("ANY/MAX specificity    =", fmt_rate(neg_any_ok, len(neg)))
print(f"ANY/MAX FPR            = {100.0*(1-any_spec):.1f}%")
print(f"ANY/MAX balanced acc   = {100.0*(any_recall+any_spec)/2.0:.1f}%")
print(f"MAX-score ROC-AUC      = {max_auc:.4f}")
print()
print("VideoMAE accuracy      =", fmt_rate(vm_correct, len(rows)))

# ---------- Per-category ----------
print()
print("=" * 110)
print("PER FINE-CATEGORY PAIRED METRICS")
print("=" * 110)
print(
    f"{'category':10s} {'pos':>3s} {'neg':>3s} "
    f"{'pos_rec_c':>11s} {'neg_spec_c':>11s} "
    f"{'pos_rec_m':>11s} {'neg_spec_m':>11s} "
    f"{'auc_c':>7s} {'pair_c':>8s} {'vm_pos':>8s} {'vm_neg':>8s}"
)

for cat in ["assault", "fight", "robbery", "burglary"]:
    g = [r for r in rows if r["fine_category"] == cat]
    gp = [r for r in g if r["actual_4class"] != "Normal"]
    gn = [r for r in g if r["actual_4class"] == "Normal"]

    pc = sum(r["edge_center_prediction"] == "Anomaly" for r in gp)
    nc = sum(r["edge_center_prediction"] == "Normal" for r in gn)
    pm = sum(r["edge_any_prediction"] == "Anomaly" for r in gp)
    nm = sum(r["edge_any_prediction"] == "Normal" for r in gn)

    auc_c = binary_auc(
        [float(r["vadclip_center_score"]) for r in g],
        [0 if r["actual_4class"] == "Normal" else 1 for r in g],
    )

    by_pair = {}
    for r in g:
        by_pair.setdefault(r["pair_key"], []).append(r)

    pair_ok = 0
    pair_total = 0
    margins = []
    pos_gt_normal = 0
    for key, pair_rows in by_pair.items():
        pp = [r for r in pair_rows if r["actual_4class"] != "Normal"]
        nn = [r for r in pair_rows if r["actual_4class"] == "Normal"]
        if len(pp) == 1 and len(nn) == 1:
            pair_total += 1
            pscore = float(pp[0]["vadclip_center_score"])
            nscore = float(nn[0]["vadclip_center_score"])
            margins.append(pscore - nscore)
            if pscore > nscore:
                pos_gt_normal += 1
            if (
                pp[0]["edge_center_prediction"] == "Anomaly"
                and nn[0]["edge_center_prediction"] == "Normal"
            ):
                pair_ok += 1

    vm_pos = sum(
        str(r["videomae_correct"]).strip().lower() in ("true", "1")
        for r in gp
    )
    vm_neg = sum(
        str(r["videomae_correct"]).strip().lower() in ("true", "1")
        for r in gn
    )

    print(
        f"{cat:10s} {len(gp):3d} {len(gn):3d} "
        f"{pc:3d}/{len(gp):<3d}   {nc:3d}/{len(gn):<3d}   "
        f"{pm:3d}/{len(gp):<3d}   {nm:3d}/{len(gn):<3d}   "
        f"{auc_c:7.4f} "
        f"{pair_ok:3d}/{pair_total:<3d} "
        f"{vm_pos:3d}/{len(gp):<3d} "
        f"{vm_neg:3d}/{len(gn):<3d}"
    )
    if margins:
        print(
            f"  pair discrimination: positive_score > paired_normal "
            f"{pos_gt_normal}/{pair_total}; "
            f"median(center positive-normal margin)={statistics.median(margins):.4f}"
        )

# ---------- System failure decomposition ----------
print()
print("=" * 110)
print("SYSTEM FAILURE DECOMPOSITION - CENTER")
print("=" * 110)
case_order = ["BOTH_OK", "VIDEOMAE_ONLY_FAIL", "EDGE_ONLY_FAIL", "BOTH_FAIL"]
for case in case_order:
    g = [r for r in rows if r["system_case_center"] == case]
    print(f"{case:20s}: {len(g):2d}/90 ({100.0*len(g)/90:.1f}%)")

print()
print("POSITIVE-ONLY FAILURE DECOMPOSITION - CENTER")
for case in case_order:
    g = [r for r in pos if r["system_case_center"] == case]
    print(f"{case:20s}: {len(g):2d}/45 ({100.0*len(g)/45:.1f}%)")

print()
print("=" * 110)
print("LOWEST POSITIVE CENTER SCORES")
print("=" * 110)
for r in sorted(pos, key=lambda x: float(x["vadclip_center_score"]))[:15]:
    print(
        f"{r['fine_category']:9s} {r['video']:55s} "
        f"center={float(r['vadclip_center_score']):.4f} "
        f"max={float(r['vadclip_max_score']):.4f} "
        f"edge={r['edge_center_prediction']:7s} "
        f"vm={r['videomae_prediction']:8s}"
    )

print()
print("=" * 110)
print("HIGHEST NORMAL CENTER SCORES")
print("=" * 110)
for r in sorted(neg, key=lambda x: float(x["vadclip_center_score"]), reverse=True)[:15]:
    print(
        f"{r['fine_category']:9s} {r['video']:55s} "
        f"center={float(r['vadclip_center_score']):.4f} "
        f"max={float(r['vadclip_max_score']):.4f} "
        f"edge={r['edge_center_prediction']:7s} "
        f"vm={r['videomae_prediction']:8s}"
    )

print()
print("OUTPUT =", OUT)
print("STATUS=PASS")
