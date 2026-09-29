import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent
rows = [
    json.loads(line)
    for line in (ROOT / "quality_results" / "results.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
    if line.strip()
]
quality = [row for row in rows if row.get("kind") == "quality"]
by_condition = {
    condition: [row for row in quality if row["condition"] == condition]
    for condition in ("mp4v", "h264_600k")
}

result = {"conditions": {}}
for condition, selected in by_condition.items():
    result["conditions"][condition] = {
        "video_count": len(selected),
        "psnr_mean_db": statistics.mean(row["psnr_mean_db"] for row in selected),
        "psnr_worst_video_mean_db": min(
            row["psnr_mean_db"] for row in selected
        ),
        "psnr_video_mean_pass_count": sum(
            row["psnr_mean_db"] >= 30.0 for row in selected
        ),
        "ssim_mean": statistics.mean(row["ssim_mean"] for row in selected),
        "ssim_worst_video_mean": min(row["ssim_mean"] for row in selected),
        "ssim_video_mean_pass_count": sum(
            row["ssim_mean"] >= 0.95 for row in selected
        ),
        "mean_size_bytes": statistics.mean(row["size_bytes"] for row in selected),
        "ssim_below_0_95": [
            row["video"] for row in selected if row["ssim_mean"] < 0.95
        ],
    }

mp4v = {row["video"]: row for row in by_condition["mp4v"]}
h264 = {row["video"]: row for row in by_condition["h264_600k"]}
if set(mp4v) != set(h264) or len(mp4v) != 30:
    raise RuntimeError("코덱별 30영상 짝 비교 데이터가 완전하지 않음")

result["h264_vs_mp4v"] = {
    "mean_psnr_delta_db": statistics.mean(
        h264[name]["psnr_mean_db"] - mp4v[name]["psnr_mean_db"] for name in mp4v
    ),
    "mean_ssim_delta": statistics.mean(
        h264[name]["ssim_mean"] - mp4v[name]["ssim_mean"] for name in mp4v
    ),
    "mean_size_reduction_percent": (
        1.0
        - result["conditions"]["h264_600k"]["mean_size_bytes"]
        / result["conditions"]["mp4v"]["mean_size_bytes"]
    )
    * 100.0,
}
result["aggregate_gate"] = {
    "psnr_threshold_db": 30.0,
    "ssim_threshold": 0.95,
    "h264_pass": (
        result["conditions"]["h264_600k"]["psnr_mean_db"] >= 30.0
        and result["conditions"]["h264_600k"]["ssim_mean"] >= 0.95
    ),
}

(ROOT / "quality_results" / "analysis.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
    newline="\n",
)
print(json.dumps(result, ensure_ascii=False, indent=2))
