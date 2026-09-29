#!/usr/bin/env bash
set -euo pipefail

BUNDLE_DIR=$(cd "$(dirname "$0")" && pwd)
CANDIDATE="$BUNDLE_DIR/candidate"
CODE_DIR=${CODE_DIR:-/home/hpc/drone_2026/code}

for file in uploader.py h264_encoder_worker.py start_all.sh restart_component.sh; do
  if [[ ! -f "$CANDIDATE/$file" ]]; then
    echo "후보 파일 없음: $CANDIDATE/$file" >&2
    exit 1
  fi
done
for file in ring_buffer.py state_store.py main.py; do
  if [[ ! -f "$CODE_DIR/$file" ]]; then
    echo "운영 의존 파일 없음: $CODE_DIR/$file" >&2
    exit 1
  fi
done

python3 -m py_compile "$CANDIDATE/uploader.py" "$CANDIDATE/h264_encoder_worker.py"
bash -n "$CANDIDATE/start_all.sh"
bash -n "$CANDIDATE/restart_component.sh"
grep -Fq 'CLIP_ENCODER="${CLIP_ENCODER:-h264}"' "$CANDIDATE/start_all.sh"
grep -Fq 'H264_BITRATE="${H264_BITRATE:-600000}"' "$CANDIDATE/start_all.sh"
grep -Fq 'CLIP_ENCODER="${CLIP_ENCODER:-h264}"' "$CANDIDATE/restart_component.sh"
grep -Fq 'H264_BITRATE="${H264_BITRATE:-600000}"' "$CANDIDATE/restart_component.sh"
gst-inspect-1.0 nvv4l2h264enc >/dev/null

mapfile -t MAIN_PIDS < <(pgrep -f '^python3 main.py$')
if [[ ${#MAIN_PIDS[@]} -ne 1 ]]; then
  echo "운영 main.py PID를 하나로 확정할 수 없음: ${MAIN_PIDS[*]:-none}" >&2
  exit 1
fi
MAIN_PID=${MAIN_PIDS[0]}
MAIN_ENCODER=$(tr '\0' '\n' <"/proc/$MAIN_PID/environ" | sed -n 's/^CLIP_ENCODER=//p' | tail -1)
MAIN_ENCODER=${MAIN_ENCODER:-mp4v}

echo "preflight=PASS"
echo "main_pid=$MAIN_PID"
echo "current_encoder=$MAIN_ENCODER"
echo "candidate_encoder=h264"
echo "candidate_bitrate=600000"
sha256sum "$CANDIDATE/uploader.py" "$CANDIDATE/h264_encoder_worker.py" \
  "$CANDIDATE/start_all.sh" "$CANDIDATE/restart_component.sh"
