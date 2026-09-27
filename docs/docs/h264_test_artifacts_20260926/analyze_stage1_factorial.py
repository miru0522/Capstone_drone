"""H264 2x2 저장소 요인 시험 JSONL을 재계산한다."""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def percentile(values, percent):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percent / 100) * len(ordered) + 0.999999) - 1))
    return ordered[index]


rows = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
encodes = [row for row in rows if row.get("kind") == "encode"]
memories = [row for row in rows if row.get("kind") == "memory_snapshot"]
groups = defaultdict(list)
for row in encodes:
    groups[row["condition"]].append(row)

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
        "shm_free_min_bytes": min(row["shm_free_bytes"] for row in memories),
    },
    "conditions": {},
}

for condition, condition_rows in groups.items():
    metrics = {}
    derived = {
        "total_sec": [row["total_sec"] for row in condition_rows],
        "worker_encode_sec": [row["worker_encode_sec"] for row in condition_rows],
        "non_worker_sec": [row["total_sec"] - row["worker_encode_sec"] for row in condition_rows],
        "succeeded_tail_sec": [row["total_sec"] - row["state_last_elapsed_sec"] for row in condition_rows],
        "response_write_to_parent_return_sec": [row["response_write_to_parent_return_sec"] for row in condition_rows],
    }
    for name, values in derived.items():
        metrics[name] = {
            "p50": statistics.median(values),
            "p95": percentile(values, 95),
            "max": max(values),
        }
    metrics["count"] = len(condition_rows)
    metrics["paths_valid"] = all(
        row["state_dir_actual"] == ("/dev/shm" if "state_shm" in condition else "/tmp")
        and row["response_dir_actual"] == ("/dev/shm" if "response_shm" in condition else "/tmp")
        for row in condition_rows
    )
    metrics["status_all_ok"] = all(row["state_status"] == "ok" for row in condition_rows)
    result["conditions"][condition] = metrics

baseline = result["conditions"]["state_tmp_response_tmp"]["total_sec"]["p50"]
for condition, metrics in result["conditions"].items():
    metrics["p50_improvement_vs_tmp_tmp_percent"] = (
        1.0 - metrics["total_sec"]["p50"] / baseline
    ) * 100.0

print(json.dumps(result, ensure_ascii=False, indent=2))
