#!/usr/bin/env python3
import importlib.util
import threading
import time
import numpy as np
from pathlib import Path

CODE_DIR = Path("/home/hpc/drone_2026/code")
V5 = CODE_DIR / "122_edge_runtime_jetson_v5_async_upload.py"

if not V5.exists():
    raise SystemExit(f"ERROR: missing {V5}")

spec = importlib.util.spec_from_file_location("runtime_v5", V5)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# Avoid any real stream uploader/network side effects in constructor.
m.StreamUploader.start = lambda self: None
m.StreamUploader.stop = lambda self: None

class DummyHover:
    def hover_now(self):
        pass

# Fake slow server call: blocks only upload worker for 3 seconds.
upload_started = threading.Event()
upload_finished = threading.Event()

def fake_upload_clip_sync(snapshot, anomaly_score=None):
    upload_started.set()
    time.sleep(3.0)
    upload_finished.set()
    return {"ok": True, "fake": True}

m.upload_clip_sync = fake_upload_clip_sync

# Fake fast inference that records progress and never triggers another anomaly.
inference_times = []

def fake_detect_anomaly(window):
    inference_times.append(time.time())
    time.sleep(0.05)
    return 0.0

m.detect_anomaly = fake_detect_anomaly

p = m.CameraAnomalyPipeline(DummyHover())
p._running = True

upload_thread = threading.Thread(target=p._upload_loop, daemon=True)
infer_thread = threading.Thread(target=p._inference_loop, daemon=True)
upload_thread.start()
infer_thread.start()

# Submit first upload.
first_ok = p._submit_upload([], 0.99)
if not first_ok:
    raise SystemExit("ERROR: first upload submit failed")

if not upload_started.wait(timeout=1.0):
    raise SystemExit("ERROR: upload worker did not start")

# While fake upload is sleeping, second upload must be rejected.
second_ok = p._submit_upload([], 0.88)

# Submit multiple inference jobs while upload is still blocked.
dummy = np.zeros((1, 1, 1, 3), dtype=np.uint8)
for _ in range(6):
    p._submit_inference(dummy)
    time.sleep(0.12)

time.sleep(0.4)
processed_during_upload = len(inference_times)

if not upload_finished.wait(timeout=5.0):
    raise SystemExit("ERROR: fake upload did not finish")

# After upload finishes, a new upload should be accepted again.
time.sleep(0.1)
third_ok = p._submit_upload([], 0.77)

# Let second fake upload begin, then stop.
time.sleep(0.2)
p._running = False

print("=" * 88)
print("V5 ASYNC-UPLOAD OFFLINE SMOKE")
print("=" * 88)
print("first_upload_submit =", first_ok)
print("second_upload_while_busy_submit =", second_ok)
print("inference_processed_while_upload_busy =", processed_during_upload)
print("third_upload_after_finish_submit =", third_ok)

passed = (
    first_ok is True
    and second_ok is False
    and processed_during_upload >= 3
    and third_ok is True
)

print("EXPECTED:")
print("  first=True")
print("  second=False")
print("  inference_processed>=3")
print("  third=True")
print("STATUS=" + ("PASS" if passed else "FAIL"))

if not passed:
    raise SystemExit(1)
