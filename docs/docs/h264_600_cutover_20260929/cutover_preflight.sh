#!/usr/bin/env bash
set -euo pipefail

BUNDLE_DIR=$(cd "$(dirname "$0")" && pwd)
CANDIDATE="$BUNDLE_DIR/candidate"
CODE_DIR=${CODE_DIR:-/home/hpc/drone_2026/code}
MANIFEST="$BUNDLE_DIR/manifest.json"

if [[ ! -f "$MANIFEST" ]]; then
  echo "manifest 없음: $MANIFEST" >&2
  exit 1
fi

for file in main.py uploader.py h264_encoder_worker.py start_all.sh restart_component.sh; do
  if [[ ! -f "$CANDIDATE/$file" ]]; then
    echo "후보 파일 없음: $CANDIDATE/$file" >&2
    exit 1
  fi
done
for file in ring_buffer.py state_store.py; do
  if [[ ! -f "$CODE_DIR/$file" ]]; then
    echo "운영 의존 파일 없음: $CODE_DIR/$file" >&2
    exit 1
  fi
done

python3 - "$MANIFEST" "$CODE_DIR" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
code_dir = Path(sys.argv[2])
baseline = json.loads(manifest_path.read_text(encoding="utf-8"))["baseline"]
for name in ("main.py", "uploader.py", "start_all.sh", "restart_component.sh"):
    path = code_dir / name
    if not path.is_file():
        raise SystemExit(f"운영 기준 파일 없음: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = baseline[name]
    if actual != expected:
        raise SystemExit(
            f"운영 파일 baseline 불일치: {name} expected={expected} actual={actual}"
        )
    print(f"baseline_match={name} sha256={actual}")
worker = code_dir / "h264_encoder_worker.py"
if worker.exists():
    raise SystemExit(f"운영에 없어야 할 worker 발견: {worker}")
print("baseline_match=h264_encoder_worker.py expected=absent actual=absent")
PY

python3 -m py_compile "$CANDIDATE/main.py" "$CANDIDATE/uploader.py" \
  "$CANDIDATE/h264_encoder_worker.py"
python3 -c 'import gi'
bash -n "$CANDIDATE/start_all.sh"
bash -n "$CANDIDATE/restart_component.sh"
grep -Fq 'CLIP_ENCODER="${CLIP_ENCODER:-h264}"' "$CANDIDATE/start_all.sh"
grep -Fq 'H264_BITRATE="${H264_BITRATE:-600000}"' "$CANDIDATE/start_all.sh"
grep -Fq 'CLIP_ENCODER="${CLIP_ENCODER:-h264}"' "$CANDIDATE/restart_component.sh"
grep -Fq 'H264_BITRATE="${H264_BITRATE:-600000}"' "$CANDIDATE/restart_component.sh"
gst-inspect-1.0 nvv4l2h264enc >/dev/null

if pgrep -f '[h]264_encoder_worker.py' >/dev/null; then
  echo "잔존 H264 worker 프로세스 발견" >&2
  exit 1
fi
if compgen -G '/dev/shm/anomaly_clip_*.bgr' >/dev/null \
  || compgen -G '/dev/shm/*.response.json' >/dev/null \
  || [[ -e /dev/shm/drone_clip_encoder_state.json ]]; then
  echo "/dev/shm H264 시험/운영 잔재 발견" >&2
  exit 1
fi

mapfile -t MAIN_PIDS < <(pgrep -f '^python3 main.py$')
if [[ ${#MAIN_PIDS[@]} -ne 1 ]]; then
  echo "운영 main.py PID를 하나로 확정할 수 없음: ${MAIN_PIDS[*]:-none}" >&2
  exit 1
fi
MAIN_PID=${MAIN_PIDS[0]}
PID_FILE="$CODE_DIR/logs/main.pid"
if [[ ! -f "$PID_FILE" ]] || [[ "$(tr -d '[:space:]' <"$PID_FILE")" != "$MAIN_PID" ]]; then
  echo "logs/main.pid와 실제 main.py PID 불일치" >&2
  exit 1
fi
MAIN_ENCODER=$(tr '\0' '\n' <"/proc/$MAIN_PID/environ" | sed -n 's/^CLIP_ENCODER=//p' | tail -1)
MAIN_ENCODER=${MAIN_ENCODER:-mp4v}

echo "preflight=PASS"
echo "main_pid=$MAIN_PID"
echo "current_encoder=$MAIN_ENCODER"
echo "candidate_encoder=h264"
echo "candidate_bitrate=600000"
echo "dev_shm_usage:"
df -B1 /dev/shm
echo "memory_snapshot:"
free -m
sha256sum "$CANDIDATE/main.py" "$CANDIDATE/uploader.py" "$CANDIDATE/h264_encoder_worker.py" \
  "$CANDIDATE/start_all.sh" "$CANDIDATE/restart_component.sh"
