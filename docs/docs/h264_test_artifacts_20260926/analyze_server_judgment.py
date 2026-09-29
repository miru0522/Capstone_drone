"""기존 서버 판정 JSONL을 재집계한다. 서버 요청은 수행하지 않는다."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "codex_quality_allvideo_results"
CONDITIONS = ("mp4v", "h264_600k")


def successful(row):
    body = row.get("body") or {}
    return row.get("status_code") == 200 and body.get("status") == "success"


videos = {}
for path in sorted(ROOT.glob("*.jsonl")):
    rows = []
    non_json = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            non_json.append(number)
            continue
        if isinstance(value, dict) and value.get("condition") in CONDITIONS:
            rows.append(value)
    by_condition = {
        condition: next(
            (row for row in rows if row["condition"] == condition and successful(row)),
            None,
        )
        for condition in CONDITIONS
    }
    videos[path.name.removesuffix(".jsonl")] = {
        "conditions": by_condition,
        "non_json_line_count": len(non_json),
        "non_json_first_line": non_json[0] if non_json else None,
    }

complete = [
    name
    for name, item in videos.items()
    if all(item["conditions"][condition] for condition in CONDITIONS)
]
missing = {
    name: [condition for condition in CONDITIONS if not item["conditions"][condition]]
    for name, item in videos.items()
    if not all(item["conditions"][condition] for condition in CONDITIONS)
}
category_changes = []
for name in complete:
    rows = videos[name]["conditions"]
    before = rows["mp4v"]["body"]["event_data"]
    after = rows["h264_600k"]["body"]["event_data"]
    if before.get("categoryId") != after.get("categoryId"):
        category_changes.append(
            {
                "video": name,
                "mp4v": {
                    "category_id": before.get("categoryId"),
                    "confidence": before.get("maeConfidence"),
                    "type": before.get("type"),
                },
                "h264_600k": {
                    "category_id": after.get("categoryId"),
                    "confidence": after.get("maeConfidence"),
                    "type": after.get("type"),
                },
            }
        )

hard_failure_files = {
    name: item["non_json_line_count"]
    for name, item in videos.items()
    if item["non_json_line_count"]
}
result = {
    "video_file_count": len(videos),
    "mp4v_h264_600k_complete_count": len(complete),
    "complete_videos": complete,
    "missing_conditions": missing,
    "category_change_count": len(category_changes),
    "category_changes": category_changes,
    "hard_failure_files": hard_failure_files,
    "interpretation": {
        "Assault006_x264.mp4": (
            "h264_600k 결과는 없지만 동일 내용·동일 원본 크기의 "
            "01_Violence_Assault_Assault006_x264.mp4에서 성공했다."
        ),
        "Burglary017_x264.mp4": "h264_600k 결과가 없으며 180초 ReadTimeout 흔적이 있다.",
    },
}

(ROOT / "analysis_corrected.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
    newline="\n",
)
print(json.dumps(result, ensure_ascii=False, indent=2))
