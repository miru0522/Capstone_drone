#!/usr/bin/env python3
"""
126_smoke_edge_runtime_v6_csi_e2e.py

REAL CSI + REAL TensorRT VadCLIP + REAL /analyze-video test for v6.
No real hover command. No MJPEG/continuous stream upload.

The real server call is followed by a deliberate 12-second hold inside the
upload worker. During that hold, live CSI capture and VadCLIP inference must
continue. This specifically verifies the v6 reduced-resolution upload snapshot
prevents the Argus memory failure seen in test 124.
"""

from pathlib import Path
import importlib.util
import threading
import time
import json

CODE_DIR = Path("/home/hpc/drone_2026/code")
V6 = CODE_DIR / "125_edge_runtime_jetson_v6_memory_safe_upload.py"
OUT = Path("/home/hpc/drone_2026/logs/v6_csi_e2e_smoke_126.json")

HOLD_AFTER_SERVER_SEC = 12.0
OVERLAP_OBSERVE_SEC = 10.0
PREP_TIMEOUT_SEC = 40.0

if not V6.exists():
    raise SystemExit(f"ERROR: missing v6 runtime: {V6}")

spec = importlib.util.spec_from_file_location("runtime_v6", V6)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

m.STREAM_ENABLED = False
m.StreamUploader.start = lambda self: None
m.StreamUploader.stop = lambda self: None


class DummyHover:
    def __init__(self):
        self.calls = 0

    def hover_now(self):
        self.calls += 1
        print("[SMOKE] DummyHover only - no real flight command", flush=True)


orig_detect = m.detect_anomaly
infer_lock = threading.Lock()
infer_times = []
infer_scores = []

def counted_detect(window):
    score = float(orig_detect(window))
    now = time.time()
    with infer_lock:
        infer_times.append(now)
        infer_scores.append(score)
        n = len(infer_times)
    print(f"[SMOKE] real VadCLIP inference #{n} score={score:.6f}", flush=True)
    return score

m.detect_anomaly = counted_detect


orig_upload = m.upload_clip_sync
upload_started = threading.Event()
server_returned = threading.Event()
worker_released = threading.Event()
upload_info = {"result": None, "elapsed": None}

def wrapped_upload(snapshot, anomaly_score=None):
    upload_started.set()
    shape = None
    if snapshot:
        shape = tuple(snapshot[0].frame.shape)
    print(
        f"[SMOKE] REAL upload start: frames={len(snapshot)} first_shape={shape} "
        f"score={float(anomaly_score):.6f}",
        flush=True,
    )

    t0 = time.time()
    result = orig_upload(snapshot, anomaly_score=anomaly_score)
    elapsed = time.time() - t0
    upload_info["result"] = result
    upload_info["elapsed"] = elapsed
    server_returned.set()

    print(
        f"[SMOKE] server returned in {elapsed:.2f}s; "
        f"holding reduced snapshot for {HOLD_AFTER_SERVER_SEC:.1f}s",
        flush=True,
    )
    time.sleep(HOLD_AFTER_SERVER_SEC)
    worker_released.set()
    return result

m.upload_clip_sync = wrapped_upload

hover = DummyHover()
pipeline = m.CameraAnomalyPipeline(hover)
run_exc = {"exc": None}

def run_pipeline():
    try:
        pipeline.run()
    except BaseException as e:
        run_exc["exc"] = repr(e)
        print("[SMOKE] pipeline exception:", repr(e), flush=True)


print("=" * 100)
print("126 V6 MEMORY-SAFE REAL CSI + SERVER E2E SMOKE")
print("=" * 100)
print("V6 =", V6)
print("upload clip target =", m.UPLOAD_CLIP_WIDTH, "x", m.UPLOAD_CLIP_HEIGHT)
print("No real hover command will be sent.")
print()

pipeline.initialize_camera()
print("[SMOKE] CSI first frame PASS", flush=True)

m.get_anomaly_pipeline().warmup()
print("[SMOKE] TRT VadCLIP warmup PASS", flush=True)

runner = threading.Thread(target=run_pipeline, name="smoke-v6-runner", daemon=True)
runner.start()

deadline = time.time() + PREP_TIMEOUT_SEC
while time.time() < deadline:
    with infer_lock:
        n_infer = len(infer_times)
    if len(pipeline.buffer) >= m.BUFFER_MAXLEN and n_infer >= 1:
        break
    if run_exc["exc"] is not None:
        raise RuntimeError(f"runtime failed during prep: {run_exc['exc']}")
    time.sleep(0.25)

with infer_lock:
    infer_before = len(infer_times)

if len(pipeline.buffer) < m.BUFFER_MAXLEN:
    pipeline.stop()
    raise SystemExit(
        f"ERROR: buffer did not fill: {len(pipeline.buffer)}/{m.BUFFER_MAXLEN}"
    )

if infer_before < 1:
    pipeline.stop()
    raise SystemExit("ERROR: no real inference before upload")

# Important: exercise v6's real reduced-snapshot path.
prep_t0 = time.time()
snapshot = pipeline._make_upload_snapshot()
snapshot_prep_sec = time.time() - prep_t0

if not snapshot:
    pipeline.stop()
    raise SystemExit("ERROR: reduced snapshot empty")

first_shape = tuple(snapshot[0].frame.shape)
expected_shape = (m.UPLOAD_CLIP_HEIGHT, m.UPLOAD_CLIP_WIDTH, 3)

print(
    f"[SMOKE] reduced snapshot PASS: frames={len(snapshot)} "
    f"shape={first_shape} prep={snapshot_prep_sec:.3f}s",
    flush=True,
)

if first_shape != expected_shape:
    pipeline.stop()
    raise SystemExit(
        f"ERROR: reduced shape mismatch: {first_shape} != {expected_shape}"
    )

newest_before = pipeline.buffer.get_full_buffer()[-1].timestamp
submitted = pipeline._submit_upload(snapshot, 0.999)
print("[SMOKE] controlled upload submitted =", submitted, flush=True)

# Drop caller reference. Queue/worker retains what it needs.
del snapshot

if not submitted:
    pipeline.stop()
    raise SystemExit("ERROR: upload submit failed")

if not upload_started.wait(timeout=3.0):
    pipeline.stop()
    raise SystemExit("ERROR: upload worker did not start")

if not server_returned.wait(timeout=190.0):
    pipeline.stop()
    raise SystemExit("ERROR: real server did not return in 190s")

with infer_lock:
    infer_at_server_return = len(infer_times)

# Fixed overlap window while upload worker still owns reduced snapshot.
time.sleep(OVERLAP_OBSERVE_SEC)

with infer_lock:
    infer_after_overlap = len(infer_times)

buf_now = pipeline.buffer.get_full_buffer()
newest_after = buf_now[-1].timestamp if buf_now else newest_before

inference_advance = infer_after_overlap - infer_at_server_return
capture_advance_sec = newest_after - newest_before
busy_during_hold = pipeline._upload_busy.is_set()

print()
print("[SMOKE] OVERLAP CHECK")
print("  inference_before_upload =", infer_before)
print("  inference_at_server_return =", infer_at_server_return)
print("  inference_10s_into_hold =", infer_after_overlap)
print("  inference_advance_during_busy_hold =", inference_advance)
print(f"  capture_timestamp_advance_sec = {capture_advance_sec:.2f}")
print("  upload_busy_during_hold =", busy_during_hold)

if not worker_released.wait(timeout=10.0):
    pipeline.stop()
    raise SystemExit("ERROR: upload worker did not release")

time.sleep(0.5)
busy_after = pipeline._upload_busy.is_set()

pipeline.stop()
runner.join(timeout=5.0)
pipeline.release_camera()

with infer_lock:
    final_infer = len(infer_times)

server_ok = upload_info["result"] is not None
passed = (
    server_ok
    and first_shape == expected_shape
    and snapshot_prep_sec < 5.0
    and inference_advance >= 1
    and capture_advance_sec >= 8.0
    and busy_during_hold is True
    and busy_after is False
    and run_exc["exc"] is None
)

summary = {
    "status": "PASS" if passed else "FAIL",
    "upload_resolution": f"{m.UPLOAD_CLIP_WIDTH}x{m.UPLOAD_CLIP_HEIGHT}",
    "snapshot_prep_sec": snapshot_prep_sec,
    "real_server_result_nonnull": bool(server_ok),
    "server_elapsed_sec": upload_info["elapsed"],
    "inference_before_upload": infer_before,
    "inference_at_server_return": infer_at_server_return,
    "inference_after_10s_hold": infer_after_overlap,
    "inference_advance_during_busy_hold": inference_advance,
    "capture_timestamp_advance_sec": capture_advance_sec,
    "upload_busy_during_hold": bool(busy_during_hold),
    "upload_busy_after_release": bool(busy_after),
    "final_inference_count": final_infer,
    "pipeline_exception": run_exc["exc"],
    "dummy_hover_calls": hover.calls,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

print()
print("=" * 100)
print("SUMMARY")
print("=" * 100)
for k, v in summary.items():
    print(f"{k} = {v}")
print("OUTPUT =", OUT)
print("STATUS=" + ("PASS" if passed else "FAIL"))

if not passed:
    raise SystemExit(1)
