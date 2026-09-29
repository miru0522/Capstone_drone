#!/usr/bin/env bash
set -euo pipefail

UPLOADER_SOURCE=${1:?"검증할 uploader.py 경로 필요"}
WORKER_SOURCE=${2:?"검증할 h264_encoder_worker.py 경로 필요"}
VIDEO_ROOT=${3:?"전체 영상 루트 필요"}
RESULT_DIR=${4:?"결과 디렉터리 필요"}
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORK=/tmp/codex_h264_pixel_quality_600

mapfile -t MAIN_PIDS < <(pgrep -f '^python3 main.py$')
if [[ ${#MAIN_PIDS[@]} -ne 1 ]]; then
  echo "운영 main.py PID를 하나로 확정할 수 없음: ${MAIN_PIDS[*]:-none}" >&2
  exit 1
fi
MAIN_PID=${MAIN_PIDS[0]}
MAIN_ENCODER=$(tr '\0' '\n' <"/proc/$MAIN_PID/environ" | sed -n 's/^CLIP_ENCODER=//p' | tail -1)
MAIN_ENCODER=${MAIN_ENCODER:-mp4v}
if [[ "$MAIN_ENCODER" == "h264" ]]; then
  echo "운영 main.py가 이미 H264 사용 중이므로 격리 품질 시험 중단" >&2
  exit 1
fi

for path in "$UPLOADER_SOURCE" "$WORKER_SOURCE"; do
  if [[ ! -f "$path" ]]; then
    echo "필수 파일 없음: $path" >&2
    exit 1
  fi
done
if [[ ! -d "$VIDEO_ROOT" ]]; then
  echo "영상 루트 없음: $VIDEO_ROOT" >&2
  exit 1
fi

mkdir -p "$WORK" "$RESULT_DIR"
cp "$UPLOADER_SOURCE" "$WORK/uploader.py"
cp "$WORKER_SOURCE" "$WORK/h264_encoder_worker.py"
cp /home/hpc/drone_2026/code/ring_buffer.py "$WORK/"
cp /home/hpc/drone_2026/code/state_store.py "$WORK/"
cp "$SCRIPT_DIR/research_h264_worker.py" "$WORK/"
cp "$SCRIPT_DIR/stage1_storage_factorial.py" "$WORK/"
cp "$SCRIPT_DIR/pixel_quality_600.py" "$WORK/"
python3 -m py_compile "$WORK"/*.py

cd "$WORK"
python3 pixel_quality_600.py "$VIDEO_ROOT" "$RESULT_DIR/results.jsonl"

if ! kill -0 "$MAIN_PID" 2>/dev/null; then
  echo "품질 시험 중 운영 main.py 종료 감지" >&2
  exit 1
fi
