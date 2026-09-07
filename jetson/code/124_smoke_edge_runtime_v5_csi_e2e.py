#!/usr/bin/env python3
"""
124_smoke_edge_runtime_v5_csi_e2e.py

Controlled integration smoke for VadCLIP Jetson runtime v5:
- REAL CSI camera
- REAL TensorRT VadCLIP inference
- REAL /analyze-video upload
- NO real drone hover (DummyHover)
- NO MJPEG server / no continuous StreamUploader
- Force exactly one clip upload after the ring buffer is full
- Hold the upload worker for 12 seconds after the real server response so we can
  prove CSI capture + VadCLIP inference continue while the upload worker is busy.
"""

from pathlib import Path
import importlib.util
import threading
import time
import json
import sys

CODE_DIR = Path("/home/hpc/drone_2026/code")
V5 = CODE_DIR / "122_edge_runtime_jetson_v5_async_upload.py"
OUT = Path("/home/hpc/drone_2026/logs/v5_csi_e2e_smoke_124.json")

HOLD_AFTER_SERVER_SEC = 12.0
PREP_TIMEOUT_SEC = 35.0
OVERLAP_OBSERVE_SEC = 10.0

if not V5.exists():
    raise SystemExit(f"ERROR: missing v5 runtime: {V5}")

spec = importlib.util.spec_from_file_location("runtime_v5", V5)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# Disable side-channel streaming for this smoke.
m.STREAM_ENABLED = False
m.StreamUploader.start = lambda self: None
m.StreamUploader.stop = lambda self: None


class DummyHover:
    def __init__(self):
        self.calls = 0

    def hover_now(self):
        self.calls += 1
        print("[SMOKE] DummyHover.hover_now() - real drone command suppressed", flush=True)


# ----------------------------------------------------------------------
# Instrument real VadCLIP inference.
# ----------------------------------------------------------------------
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
    print(
        f"[SMOKE] real VadCLIP inference #{len(infer_times)} score={score:.6f}",
        flush=True,
    )
    return score

m.detect_anomaly = counted_detect


# ----------------------------------------------------------------------
# Instrument REAL server upload, then deliberately hold worker 12 sec.
# ----------------------------------------------------------------------
orig_upload = m.upload_clip_sync
upload_started = threading.Event()
server_returned = threading.Event()
upload_worker_released = threading.Event()
upload_result_holder = {"result": None, "server_elapsed_sec": None}

def wrapped_real_upload(snapshot, anomaly_score=None):
    upload_started.set()
    t0 = time.time()
    print(
        f"[SMOKE] REAL /analyze-video upload started: frames={len(snapshot)} "
        f"score={float(anomaly_score):.6f}",
        flush=True,
    )

    result = orig_upload(snapshot, anomaly_score=anomaly_score)
    elapsed = time.time() - t0
    upload_result_holder["result"] = result
    upload_result_holder["server_elapsed_sec"] = elapsed
    server_returned.set()

    print(
        f"[SMOKE] REAL server call returned in {elapsed:.2f}s; "
        f"holding upload worker for {HOLD_AFTER_SERVER_SEC:.1f}s",
        flush=True,
    )
    time.sleep(HOLD_AFTER_SERVER_SEC)
    upload_worker_released.set()
    return result

m.upload_clip_sync = wrapped_real_upload


hover = DummyHover()
pipeline = m.CameraAnomalyPipeline(hover)

run_exc = {"exc": None}

def run_pipeline():
    try:
        pipeline.run()
    except BaseException as e:
        run_exc["exc"] = repr(e)
        print("[SMOKE] pipeline.run exception:", repr(e), flush=True)


print("=" * 100)
print("124 V5 REAL CSI + REAL SERVER E2E SMOKE")
print("=" * 100)
print("V5 =", V5)
print("Analyze URL =", getattr(m, "ANALYZE_URL", "<from uploader module>"))
print("This smoke DOES NOT send a real hover command.")
print()

# Important Xavier rule: camera first, model second.
pipeline.initialize_camera()
print("[SMOKE] CSI first frame PASS", flush=True)

m.get_anomaly_pipeline().warmup()
print("[SMOKE] TRT VadCLIP warmup PASS", flush=True)

runner = threading.Thread(target=run_pipeline, name="smoke-v5-runner", daemon=True)
runner.start()

# Wait until ring buffer is full and at least one real inference has completed.
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
    infer_before_upload = len(infer_times)

if len(pipeline.buffer) < m.BUFFER_MAXLEN:
    pipeline.stop()
    raise SystemExit(
        f"ERROR: ring buffer did not fill in time: "
        f"{len(pipeline.buffer)}/{m.BUFFER_MAXLEN}"
    )

if infer_before_upload < 1:
    pipeline.stop()
    raise SystemExit("ERROR: no real VadCLIP inference completed before upload test")

snapshot = pipeline.buffer.get_full_buffer()
newest_before = snapshot[-1].timestamp
print(
    f"[SMOKE] prep PASS: buffer={len(snapshot)} "
    f"inference_count={infer_before_upload}",
    flush=True,
)

# Controlled upload submission. No actual hover command.
submitted = pipeline._submit_upload(snapshot, 0.999)
print("[SMOKE] controlled upload submitted =", submitted, flush=True)
if not submitted:
    pipeline.stop()
    raise SystemExit("ERROR: controlled upload could not be submitted")

if not upload_started.wait(timeout=3.0):
    pipeline.stop()
    raise SystemExit("ERROR: upload worker did not start")

infer_at_upload_start = infer_before_upload

# Wait until real server returns. Runtime should continue meanwhile.
if not server_returned.wait(timeout=190.0):
    pipeline.stop()
    raise SystemExit("ERROR: real server did not return within 190 seconds")

with infer_lock:
    infer_at_server_return = len(infer_times)

# During deliberate 12-second hold, both capture and inference must continue.
time.sleep(OVERLAP_OBSERVE_SEC)

with infer_lock:
    infer_during_busy = len(infer_times)

buf_after = pipeline.buffer.get_full_buffer()
newest_after = buf_after[-1].timestamp if buf_after else newest_before
capture_advance_sec = newest_after - newest_before
inference_advance = infer_during_busy - infer_at_server_return

print()
print("[SMOKE] OVERLAP CHECK")
print("  inference_count_at_upload_start =", infer_at_upload_start)
print("  inference_count_at_server_return =", infer_at_server_return)
print("  inference_count_10s_into_hold =", infer_during_busy)
print("  inference_advance_during_busy_hold =", inference_advance)
print(f"  capture_timestamp_advance_sec = {capture_advance_sec:.2f}")
print("  upload_busy =", pipeline._upload_busy.is_set())

# Wait remaining hold and ensure worker releases.
if not upload_worker_released.wait(timeout=5.0):
    # It may already be close to release; allow a little extra.
    if not upload_worker_released.wait(timeout=10.0):
        pipeline.stop()
        raise SystemExit("ERROR: upload worker did not release after hold")

time.sleep(0.5)
busy_after = pipeline._upload_busy.is_set()

pipeline.stop()
runner.join(timeout=5.0)
pipeline.release_camera()

with infer_lock:
    final_infer_count = len(infer_times)

server_ok = upload_result_holder["result"] is not None
passed = (
    submitted
    and server_ok
    and inference_advance >= 1
    and capture_advance_sec >= 5.0
    and busy_after is False
    and run_exc["exc"] is None
)

summary = {
    "status": "PASS" if passed else "FAIL",
    "real_server_result_nonnull": bool(server_ok),
    "server_elapsed_sec": upload_result_holder["server_elapsed_sec"],
    "inference_count_before_upload": infer_before_upload,
    "inference_count_at_server_return": infer_at_server_return,
    "inference_count_during_busy_hold": infer_during_busy,
    "inference_advance_during_busy_hold": inference_advance,
    "capture_timestamp_advance_sec": capture_advance_sec,
    "upload_busy_after_release": bool(busy_after),
    "final_inference_count": final_infer_count,
    "pipeline_exception": run_exc["exc"],
    "dummy_hover_calls": hover.calls,
    "note": (
        "Real CSI + real TRT VadCLIP + real /analyze-video. "
        "Upload worker intentionally held after server response to verify "
        "capture/inference continue independently."
    ),
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
