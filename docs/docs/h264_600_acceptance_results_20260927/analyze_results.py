import json
import math
import re
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def percentile(values, percent):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percent / 100.0) - 1)]


rows = [
    json.loads(line)
    for line in (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines()
]
encodes = [row for row in rows if row.get("kind") == "encode"]
h264 = sorted(
    [row for row in encodes if row["condition"] == "h264_600k"],
    key=lambda row: row["sequence"],
)
mp4v = [row for row in encodes if row["condition"] == "mp4v"]

pairs = {}
for row in encodes:
    key = (row["phase"], row["video"], row["repeat"])
    pairs.setdefault(key, {})[row["condition"]] = row
if not all(set(pair) == {"mp4v", "h264_600k"} for pair in pairs.values()):
    raise RuntimeError("짝 비교 누락")

pair_improvements = [
    (1.0 - pair["h264_600k"]["total_sec"] / pair["mp4v"]["total_sec"])
    * 100.0
    for pair in pairs.values()
]

per_video = {}
for video in sorted({row["video"] for row in encodes}):
    selected = [
        pair
        for (phase, pair_video, _), pair in pairs.items()
        if phase == "all_videos" and pair_video == video
    ]
    improvements = [
        (1.0 - pair["h264_600k"]["total_sec"] / pair["mp4v"]["total_sec"])
        * 100.0
        for pair in selected
    ]
    per_video[video] = {
        "pair_count": len(selected),
        "median_improvement_percent": statistics.median(improvements),
        "min_improvement_percent": min(improvements),
        "max_improvement_percent": max(improvements),
    }

warm_uploader = [row["uploader"] for row in encodes[10:] if row.get("uploader")]
warm_worker = [row["worker"] for row in h264[5:] if row.get("worker")]

temperature_values = {}
for line in (ROOT / "tegrastats.log").read_text(encoding="utf-8").splitlines():
    for name, value in re.findall(r"([A-Za-z_]+)@([0-9.]+)C", line):
        temperature_values.setdefault(name, []).append(float(value))

result = {
    "encode_count": len(encodes),
    "condition_counts": {"mp4v": len(mp4v), "h264_600k": len(h264)},
    "paired": {
        "count": len(pair_improvements),
        "median_improvement_percent": statistics.median(pair_improvements),
        "p05_improvement_percent": percentile(pair_improvements, 5),
        "min_improvement_percent": min(pair_improvements),
        "pairs_at_least_20_percent": sum(value >= 20.0 for value in pair_improvements),
        "pairs_slower_than_mp4v": sum(value < 0.0 for value in pair_improvements),
    },
    "h264_drift": {
        "first25_p95_sec": percentile([row["total_sec"] for row in h264[:25]], 95),
        "last25_p95_sec": percentile([row["total_sec"] for row in h264[-25:]], 95),
    },
    "resources": {
        "uploader_rss_min_kib": min(item["rss_kib"] for item in warm_uploader),
        "uploader_rss_max_kib": max(item["rss_kib"] for item in warm_uploader),
        "uploader_fd_min": min(item["fd_count"] for item in warm_uploader),
        "uploader_fd_max": max(item["fd_count"] for item in warm_uploader),
        "uploader_threads_min": min(item["threads"] for item in warm_uploader),
        "uploader_threads_max": max(item["threads"] for item in warm_uploader),
        "worker_rss_min_kib": min(item["rss_kib"] for item in warm_worker),
        "worker_rss_max_kib": max(item["rss_kib"] for item in warm_worker),
        "worker_fd_min": min(item["fd_count"] for item in warm_worker),
        "worker_fd_max": max(item["fd_count"] for item in warm_worker),
        "worker_threads_min": min(item["threads"] for item in warm_worker),
        "worker_threads_max": max(item["threads"] for item in warm_worker),
    },
    "temperature": {
        name: {
            "mean_c": statistics.mean(values),
            "max_c": max(values),
        }
        for name, values in temperature_values.items()
    },
    "videos_below_20_percent": sorted(
        video
        for video, value in per_video.items()
        if value["median_improvement_percent"] < 20.0
    ),
    "videos_slower_than_mp4v": sorted(
        video
        for video, value in per_video.items()
        if value["median_improvement_percent"] < 0.0
    ),
    "per_video": per_video,
}
first = result["h264_drift"]["first25_p95_sec"]
last = result["h264_drift"]["last25_p95_sec"]
result["h264_drift"]["p95_change_percent"] = (last / first - 1.0) * 100.0

(ROOT / "analysis.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(result, ensure_ascii=False, indent=2))
