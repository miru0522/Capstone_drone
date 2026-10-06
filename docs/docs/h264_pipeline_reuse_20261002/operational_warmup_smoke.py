"""Jetson 운영 uploader의 웜업 성공과 이벤트 상태 비오염을 확인한다."""

from pathlib import Path

import uploader


state_path = Path(uploader.H264_STATE_PATH)
before = state_path.read_bytes() if state_path.exists() else None
ok = uploader.warmup_clip_encoder(960, 540, 9)
after = state_path.read_bytes() if state_path.exists() else None

print(
    {
        "ok": ok,
        "state_existed_before": before is not None,
        "state_existed_after": after is not None,
        "state_unchanged": before == after,
    }
)

if not ok:
    raise SystemExit("warmup failed")
if before != after:
    raise SystemExit("warmup changed event state")
