"""mp4v/H264 실제 함수 경계 비교 JSONL을 재계산한다."""

import json
import statistics
import sys
from pathlib import Path

def percentile(values, percent):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percent / 100) * len(ordered) + 0.999999) - 1))
    return ordered[index]


def linear_percentile(values, percent):
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100.0
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


rows = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
encodes = [row for row in rows if row.get("kind") == "encode"]
memories = [row for row in rows if row.get("kind") == "memory_snapshot"]
result = {
    "encode_count": len(encodes),
    "main_pid_all_alive": all(row["main_pid_alive"] for row in encodes),
    "main_trigger_total": sum(row["main_trigger_count"] for row in encodes),
    "main_mp4v_encode_total": sum(row["main_mp4v_encode_count"] for row in encodes),
    "main_upload_start_total": sum(row["main_upload_start_count"] for row in encodes),
    "memory": {
        "mem_available_min_kib": min(row["MemAvailable_kib"] for row in memories),
        "mem_available_max_kib": max(row["MemAvailable_kib"] for row in memories),
        "swap_used_min_kib": min(row["SwapTotal_kib"] - row["SwapFree_kib"] for row in memories),
        "swap_used_max_kib": max(row["SwapTotal_kib"] - row["SwapFree_kib"] for row in memories),
    },
    "conditions": {},
}

for condition in ("mp4v", "h264_shm_shm"):
    condition_rows = [row for row in encodes if row["condition"] == condition]
    values = [row["total_sec"] for row in condition_rows]
    sizes = [row["size_bytes"] for row in condition_rows]
    result["conditions"][condition] = {
        "count": len(values),
        "p50_sec": statistics.median(values),
        "p95_sec": percentile(values, 95),
        "p95_linear_sec": linear_percentile(values, 95),
        "max_sec": max(values),
        "size_bytes_median": statistics.median(sizes),
    }

mp4v = result["conditions"]["mp4v"]
h264 = result["conditions"]["h264_shm_shm"]
result["improvement_percent"] = {
    "p50": (1.0 - h264["p50_sec"] / mp4v["p50_sec"]) * 100.0,
    "p95": (1.0 - h264["p95_sec"] / mp4v["p95_sec"]) * 100.0,
    "p95_linear": (
        1.0 - h264["p95_linear_sec"] / mp4v["p95_linear_sec"]
    ) * 100.0,
    "max": (1.0 - h264["max_sec"] / mp4v["max_sec"]) * 100.0,
    "size": (1.0 - h264["size_bytes_median"] / mp4v["size_bytes_median"]) * 100.0,
}

h264_rows = [row for row in encodes if row["condition"] == "h264_shm_shm"]
result["h264"] = {
    "state_all_ok": all(row["state_status"] == "ok" for row in h264_rows),
    "paths_all_shm": all(
        row["state_dir_actual"] == "/dev/shm"
        and row["response_dir_actual"] == "/dev/shm"
        for row in h264_rows
    ),
    "worker_encode_p50_sec": statistics.median(
        row["worker_encode_sec"] for row in h264_rows
    ),
    "worker_encode_p95_sec": percentile(
        [row["worker_encode_sec"] for row in h264_rows], 95
    ),
}

print(json.dumps(result, ensure_ascii=False, indent=2))
