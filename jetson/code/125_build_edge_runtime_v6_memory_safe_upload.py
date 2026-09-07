#!/usr/bin/env python3
from pathlib import Path
import hashlib
import py_compile

CODE_DIR = Path("/home/hpc/drone_2026/code")
SRC = CODE_DIR / "122_edge_runtime_jetson_v5_async_upload.py"
DST = CODE_DIR / "125_edge_runtime_jetson_v6_memory_safe_upload.py"
EXPECTED_SRC_SHA256 = "744acdf913c29aa1d2143edc39c84d41cd5d3f590364ae6d439a266471d627f7"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly 1 match, found {n}")
    return text.replace(old, new, 1)

if not SRC.exists():
    raise SystemExit(f"ERROR: source not found: {SRC}")

src_sha = sha256(SRC)
print("SOURCE =", SRC)
print("SOURCE_SHA256 =", src_sha)
if src_sha != EXPECTED_SRC_SHA256:
    raise SystemExit(
        "ERROR: v5 source hash does not match frozen baseline.\n"
        f"expected={EXPECTED_SRC_SHA256}\nactual  ={src_sha}\nNo file was modified."
    )

if DST.exists():
    raise SystemExit(f"ERROR: destination already exists: {DST}\nRefusing to overwrite.")

text = SRC.read_text(encoding="utf-8")

text = replace_once(
    text,
    "# TRT V5 ASYNC-UPLOAD COPY — original main.py and v4 unchanged\n",
    "# TRT V6 MEMORY-SAFE ASYNC-UPLOAD COPY — original main.py/v4/v5 unchanged\n",
    "header",
)

text = replace_once(
    text,
    "from ring_buffer import RingBuffer, FPS, BUFFER_MAXLEN, INFER_WINDOW_LEN\n",
    "from ring_buffer import RingBuffer, FrameEntry, FPS, BUFFER_MAXLEN, INFER_WINDOW_LEN\n",
    "FrameEntry import",
)

old_logger = 'logger = logging.getLogger("main_v4_trt")\n'
new_logger = 'logger = logging.getLogger("main_v4_trt")\n\n' \
    '# V6: live CSI / VadCLIP input resolution is unchanged.\n' \
    '# Only the anomaly clip queued to the upload worker is reduced.\n' \
    'UPLOAD_CLIP_WIDTH = int(os.environ.get("UPLOAD_CLIP_WIDTH", "960"))\n' \
    'UPLOAD_CLIP_HEIGHT = int(os.environ.get("UPLOAD_CLIP_HEIGHT", "540"))\n'
text = replace_once(text, old_logger, new_logger, "upload resolution constants")

marker = "    def _handle_anomaly_score(self, score: float) -> None:\n"
method = (
    "    def _make_upload_snapshot(self):\n"
    "        full = self.buffer.get_full_buffer()\n"
    "        if not full:\n"
    "            return []\n\n"
    "        t0 = time.time()\n"
    "        reduced = []\n"
    "        full.reverse()\n"
    "        while full:\n"
    "            entry = full.pop()\n"
    "            frame_small = cv2.resize(\n"
    "                entry.frame,\n"
    "                (UPLOAD_CLIP_WIDTH, UPLOAD_CLIP_HEIGHT),\n"
    "                interpolation=cv2.INTER_AREA,\n"
    "            )\n"
    "            reduced.append(\n"
    "                FrameEntry(frame=frame_small, timestamp=entry.timestamp)\n"
    "            )\n\n"
    "        elapsed_ms = (time.time() - t0) * 1000.0\n"
    "        logger.info(\n"
    "            \"V6 upload snapshot 준비: frames=%d, resolution=%dx%d, elapsed=%.1fms\",\n"
    "            len(reduced), UPLOAD_CLIP_WIDTH, UPLOAD_CLIP_HEIGHT, elapsed_ms\n"
    "        )\n"
    "        return reduced\n\n"
)
if text.count(marker) != 1:
    raise RuntimeError(f"snapshot method marker count={text.count(marker)}")
text = text.replace(marker, method + marker, 1)

old_snapshot = (
    "        # get_full_buffer()는 FrameEntry들의 list snapshot을 반환한다.\n"
    "        # deque가 이후 갱신돼도 이 list가 frame reference를 보유하므로 안전하다.\n"
    "        snapshot = self.buffer.get_full_buffer()\n"
    "        submitted = self._submit_upload(snapshot, score)\n"
)
new_snapshot = (
    "        # V6: long-lived upload job에는 reduced snapshot만 보낸다.\n"
    "        # live ring과 VadCLIP 입력 해상도는 그대로 유지된다.\n"
    "        snapshot = self._make_upload_snapshot()\n"
    "        submitted = self._submit_upload(snapshot, score)\n"
)
text = replace_once(text, old_snapshot, new_snapshot, "use reduced snapshot")

DST.write_text(text, encoding="utf-8")
try:
    py_compile.compile(str(DST), doraise=True)
except Exception:
    try:
        DST.unlink()
    except OSError:
        pass
    raise

dst_sha = sha256(DST)
print()
print("=" * 100)
print("V6 BUILD PASS")
print("=" * 100)
print("SOURCE_UNCHANGED_SHA256 =", sha256(SRC))
print("TARGET =", DST)
print("TARGET_SHA256 =", dst_sha)
print("COMPILE_RC = 0")
print("STATIC CHECKS:")
checks = [
    "from ring_buffer import RingBuffer, FrameEntry, FPS, BUFFER_MAXLEN, INFER_WINDOW_LEN",
    'UPLOAD_CLIP_WIDTH = int(os.environ.get("UPLOAD_CLIP_WIDTH", "960"))',
    'UPLOAD_CLIP_HEIGHT = int(os.environ.get("UPLOAD_CLIP_HEIGHT", "540"))',
    "def _make_upload_snapshot(self):",
    "interpolation=cv2.INTER_AREA",
    "snapshot = self._make_upload_snapshot()",
    "self._upload_queue = queue.Queue(maxsize=1)",
    "def _upload_loop(self)",
]
for s in checks:
    ok = s in text
    print(f"  {str(ok):5s}  {s}")
    if not ok:
        raise SystemExit("ERROR: static check failed")
print("STATUS=PASS")
