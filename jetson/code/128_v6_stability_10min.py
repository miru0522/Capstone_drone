#!/usr/bin/env python3
"""
128_v6_stability_10min.py

10-minute stability test for the frozen VadCLIP v6 runtime.

REAL:
- CSI camera
- TensorRT VadCLIP inference
- production /analyze-video route through 8031
- two controlled 960x540 anomaly-clip uploads

DISABLED:
- real hover / flight command
- natural anomaly-triggered uploads
- MJPEG server
- continuous StreamUploader

Pass gates:
- no pipeline exception
- capture average >= 8.0 fps over the 10-minute run
- >= 100 real VadCLIP inferences
- maximum inter-inference gap <= 12 seconds
- two controlled uploads submitted
- both uploads return non-null server JSON
- upload worker is not left busy at shutdown
"""

from pathlib import Path
import csv
import importlib.util
import json
import os
import threading
import time
import traceback

CODE_DIR = Path("/home/hpc/drone_2026/code")
V6 = CODE_DIR / "125_edge_runtime_jetson_v6_memory_safe_upload.py"

LOG_DIR = Path("/home/hpc/drone_2026/logs")
SUMMARY_PATH = LOG_DIR / "v6_stability_128_summary.json"
SAMPLES_PATH = LOG_DIR / "v6_stability_128_memory_samples.csv"

DURATION_SEC = 600.0
UPLOAD_AT_SEC = (60.0, 330.0)
MONITOR_INTERVAL_SEC = 5.0

MIN_CAPTURE_FPS = 8.0
MIN_INFERENCES = 100
MAX_INFERENCE_GAP_SEC = 12.0

if not V6.exists():
    raise SystemExit(f"ERROR: missing frozen v6 runtime: {V6}")

spec = importlib.util.spec_from_file_location("runtime_v6_stability", V6)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# No side-channel streaming in this stability test.
m.STREAM_ENABLED = False
m.StreamUploader.start = lambda self: None
m.StreamUploader.stop = lambda self: None


class DummyHover:
    def __init__(self):
        self.calls = 0

    def hover_now(self):
        self.calls += 1
        print("[STABILITY] DummyHover only - no real flight command", flush=True)


def read_meminfo():
    vals = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as f:
        for line in f:
            key, rest = line.split(":", 1)
            try:
                vals[key] = int(rest.strip().split()[0])  # kB
            except Exception:
                pass

    rss_kb = None
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
                    break
    except Exception:
        pass

    return {
        "mem_available_kb": vals.get("MemAvailable"),
        "mem_free_kb": vals.get("MemFree"),
        "swap_free_kb": vals.get("SwapFree"),
        "process_rss_kb": rss_kb,
    }


# ----------------------------------------------------------------------
# Instrument real VadCLIP inference.
# ----------------------------------------------------------------------
orig_detect = m.detect_anomaly
infer_lock = threading.Lock()
infer_times = []
infer_scores = []
infer_latencies = []

def counted_detect(window):
    t0 = time.time()
    score = float(orig_detect(window))
    t1 = time.time()
    with infer_lock:
        infer_times.append(t1)
        infer_scores.append(score)
        infer_latencies.append(t1 - t0)
        n = len(infer_times)

    if n <= 3 or n % 10 == 0:
        print(
            f"[STABILITY] inference #{n} "
            f"score={score:.6f} latency={(t1-t0)*1000:.1f}ms",
            flush=True,
        )
    return score

m.detect_anomaly = counted_detect


# ----------------------------------------------------------------------
# Instrument real server uploads.
# ----------------------------------------------------------------------
orig_upload = m.upload_clip_sync
upload_lock = threading.Lock()
upload_records = []

def counted_upload(snapshot, anomaly_score=None):
    start = time.time()
    shape = tuple(snapshot[0].frame.shape) if snapshot else None
    print(
        f"[STABILITY] REAL upload start frames={len(snapshot)} "
        f"shape={shape} score={float(anomaly_score):.6f}",
        flush=True,
    )
    try:
        result = orig_upload(snapshot, anomaly_score=anomaly_score)
        elapsed = time.time() - start
        rec = {
            "started_at_epoch": start,
            "elapsed_sec": elapsed,
            "result_nonnull": result is not None,
            "result": result,
            "exception": None,
        }
        print(
            f"[STABILITY] REAL upload end elapsed={elapsed:.2f}s "
            f"result_nonnull={result is not None}",
            flush=True,
        )
        return result
    except BaseException as e:
        elapsed = time.time() - start
        rec = {
            "started_at_epoch": start,
            "elapsed_sec": elapsed,
            "result_nonnull": False,
            "result": None,
            "exception": repr(e),
        }
        print("[STABILITY] upload wrapper exception:", repr(e), flush=True)
        raise
    finally:
        with upload_lock:
            upload_records.append(rec)

m.upload_clip_sync = counted_upload


hover = DummyHover()
pipeline = m.CameraAnomalyPipeline(hover)

# Suppress natural score-triggered hover/upload. Controlled uploads below still
# exercise the real v6 reduced-snapshot + upload-worker path.
pipeline._check_trigger = lambda score: False

# Count actual frames accepted into the live ring.
capture_lock = threading.Lock()
capture_count = 0
orig_push = pipeline.buffer.push

def counted_push(frame):
    global capture_count
    orig_push(frame)
    with capture_lock:
        capture_count += 1

pipeline.buffer.push = counted_push

run_exc = {"exc": None, "traceback": None}

def run_pipeline():
    try:
        pipeline.run()
    except BaseException as e:
        run_exc["exc"] = repr(e)
        run_exc["traceback"] = traceback.format_exc()
        print("[STABILITY] pipeline exception:", repr(e), flush=True)


print("=" * 100)
print("128 V6 10-MINUTE STABILITY TEST")
print("=" * 100)
print("V6 =", V6)
print("Duration sec =", DURATION_SEC)
print("Controlled uploads at sec =", UPLOAD_AT_SEC)
print("No real hover command will be sent.")
print()

# Xavier memory rule: camera first, model second.
pipeline.initialize_camera()
print("[STABILITY] CSI first frame PASS", flush=True)

m.get_anomaly_pipeline().warmup()
print("[STABILITY] TRT VadCLIP warmup PASS", flush=True)

mem_after_warmup = read_meminfo()
print("[STABILITY] memory after warmup =", mem_after_warmup, flush=True)

runner = threading.Thread(
    target=run_pipeline,
    name="stability-v6-runner",
    daemon=True,
)
runner.start()

run_start = time.time()
last_monitor = 0.0
upload_index = 0
submitted_uploads = 0
submission_records = []
samples = []

try:
    while True:
        now = time.time()
        elapsed = now - run_start
        if elapsed >= DURATION_SEC:
            break

        if run_exc["exc"] is not None:
            print("[STABILITY] aborting monitor loop due to pipeline exception", flush=True)
            break

        # Controlled upload schedule.
        if upload_index < len(UPLOAD_AT_SEC) and elapsed >= UPLOAD_AT_SEC[upload_index]:
            if pipeline._upload_busy.is_set():
                print(
                    f"[STABILITY] upload schedule {upload_index+1} delayed: worker busy",
                    flush=True,
                )
            elif len(pipeline.buffer) < m.BUFFER_MAXLEN:
                print(
                    f"[STABILITY] upload schedule {upload_index+1} delayed: "
                    f"buffer={len(pipeline.buffer)}/{m.BUFFER_MAXLEN}",
                    flush=True,
                )
            else:
                prep_t0 = time.time()
                snapshot = pipeline._make_upload_snapshot()
                prep_sec = time.time() - prep_t0
                shape = tuple(snapshot[0].frame.shape) if snapshot else None
                submitted = pipeline._submit_upload(snapshot, 0.999)
                submission_records.append({
                    "schedule_sec": UPLOAD_AT_SEC[upload_index],
                    "actual_elapsed_sec": elapsed,
                    "snapshot_prep_sec": prep_sec,
                    "frames": len(snapshot),
                    "shape": shape,
                    "submitted": bool(submitted),
                })
                print(
                    f"[STABILITY] controlled upload #{upload_index+1} "
                    f"submitted={submitted} frames={len(snapshot)} "
                    f"shape={shape} prep={prep_sec:.3f}s",
                    flush=True,
                )
                if submitted:
                    submitted_uploads += 1
                    upload_index += 1
                # Release controller-side list reference. Queue/worker owns the job.
                del snapshot

        if elapsed - last_monitor >= MONITOR_INTERVAL_SEC:
            last_monitor = elapsed
            mem = read_meminfo()
            with capture_lock:
                frames = capture_count
            with infer_lock:
                infers = len(infer_times)

            sample = {
                "elapsed_sec": elapsed,
                "capture_count": frames,
                "inference_count": infers,
                "upload_busy": int(pipeline._upload_busy.is_set()),
                **mem,
            }
            samples.append(sample)

            if int(elapsed) % 30 < MONITOR_INTERVAL_SEC:
                fps_so_far = frames / elapsed if elapsed > 0 else 0.0
                print(
                    f"[STABILITY] t={elapsed:.1f}s frames={frames} "
                    f"fps={fps_so_far:.2f} infers={infers} "
                    f"upload_busy={pipeline._upload_busy.is_set()} "
                    f"MemAvailableMB="
                    f"{(mem['mem_available_kb']/1024):.0f}"
                    if mem["mem_available_kb"] is not None
                    else f"[STABILITY] t={elapsed:.1f}s frames={frames} "
                         f"infers={infers} upload_busy={pipeline._upload_busy.is_set()}",
                    flush=True,
                )

        time.sleep(0.10)

finally:
    # If the second upload is still finishing close to the run boundary,
    # allow a bounded grace period so the worker can report its result.
    grace_deadline = time.time() + 200.0
    while pipeline._upload_busy.is_set() and time.time() < grace_deadline:
        print("[STABILITY] waiting for final upload worker...", flush=True)
        time.sleep(2.0)

    pipeline.stop()
    runner.join(timeout=8.0)
    pipeline.release_camera()

run_end = time.time()
actual_duration = run_end - run_start

with capture_lock:
    final_capture_count = capture_count
with infer_lock:
    final_infer_times = list(infer_times)
    final_infer_scores = list(infer_scores)
    final_infer_latencies = list(infer_latencies)
with upload_lock:
    final_upload_records = list(upload_records)

capture_fps = final_capture_count / actual_duration if actual_duration > 0 else 0.0
infer_count = len(final_infer_times)

gaps = [
    b - a for a, b in zip(final_infer_times[:-1], final_infer_times[1:])
]
max_infer_gap = max(gaps) if gaps else None
mean_infer_latency = (
    sum(final_infer_latencies) / len(final_infer_latencies)
    if final_infer_latencies else None
)
max_infer_latency = max(final_infer_latencies) if final_infer_latencies else None

mem_end = read_meminfo()
min_mem_available_kb = min(
    [s["mem_available_kb"] for s in samples if s["mem_available_kb"] is not None],
    default=None,
)
peak_rss_kb = max(
    [s["process_rss_kb"] for s in samples if s["process_rss_kb"] is not None],
    default=None,
)

successful_uploads = sum(1 for r in final_upload_records if r["result_nonnull"])
upload_busy_after = pipeline._upload_busy.is_set()

gates = {
    "pipeline_exception_none": run_exc["exc"] is None,
    "duration_reached": actual_duration >= (DURATION_SEC - 5.0),
    "capture_fps_ge_min": capture_fps >= MIN_CAPTURE_FPS,
    "inference_count_ge_min": infer_count >= MIN_INFERENCES,
    "max_inference_gap_le_limit": (
        max_infer_gap is not None and max_infer_gap <= MAX_INFERENCE_GAP_SEC
    ),
    "two_uploads_submitted": submitted_uploads == 2,
    "two_uploads_successful": successful_uploads == 2,
    "upload_not_busy_after": upload_busy_after is False,
    "dummy_hover_never_called": hover.calls == 0,
}

passed = all(gates.values())

summary = {
    "status": "PASS" if passed else "FAIL",
    "v6_path": str(V6),
    "duration_requested_sec": DURATION_SEC,
    "duration_actual_sec": actual_duration,
    "capture_count": final_capture_count,
    "capture_fps": capture_fps,
    "inference_count": infer_count,
    "max_inference_gap_sec": max_infer_gap,
    "mean_inference_latency_ms": (
        mean_infer_latency * 1000.0 if mean_infer_latency is not None else None
    ),
    "max_inference_latency_ms": (
        max_infer_latency * 1000.0 if max_infer_latency is not None else None
    ),
    "submitted_uploads": submitted_uploads,
    "successful_uploads": successful_uploads,
    "submission_records": submission_records,
    "upload_records": final_upload_records,
    "memory_after_warmup": mem_after_warmup,
    "memory_end": mem_end,
    "min_mem_available_kb": min_mem_available_kb,
    "peak_process_rss_kb": peak_rss_kb,
    "pipeline_exception": run_exc["exc"],
    "pipeline_traceback": run_exc["traceback"],
    "dummy_hover_calls": hover.calls,
    "gates": gates,
}

LOG_DIR.mkdir(parents=True, exist_ok=True)

if samples:
    fieldnames = list(samples[0].keys())
    with SAMPLES_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(samples)

SUMMARY_PATH.write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print()
print("=" * 100)
print("128 STABILITY SUMMARY")
print("=" * 100)
print(f"duration_actual_sec = {actual_duration:.2f}")
print(f"capture_count = {final_capture_count}")
print(f"capture_fps = {capture_fps:.3f}")
print(f"inference_count = {infer_count}")
print(f"max_inference_gap_sec = {max_infer_gap}")
print(
    "mean_inference_latency_ms =",
    None if mean_infer_latency is None else round(mean_infer_latency * 1000.0, 2),
)
print(
    "max_inference_latency_ms =",
    None if max_infer_latency is None else round(max_infer_latency * 1000.0, 2),
)
print(f"submitted_uploads = {submitted_uploads}")
print(f"successful_uploads = {successful_uploads}")
print(f"min_mem_available_kb = {min_mem_available_kb}")
print(f"peak_process_rss_kb = {peak_rss_kb}")
print(f"pipeline_exception = {run_exc['exc']}")
print(f"dummy_hover_calls = {hover.calls}")
print("GATES:")
for k, v in gates.items():
    print(f"  {k} = {v}")
print("SUMMARY_PATH =", SUMMARY_PATH)
print("SAMPLES_PATH =", SAMPLES_PATH)
print("STATUS=" + ("PASS" if passed else "FAIL"))

raise SystemExit(0 if passed else 1)
