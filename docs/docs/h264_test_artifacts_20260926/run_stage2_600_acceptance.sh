#!/usr/bin/env bash
set -euo pipefail

UPLOADER_SOURCE=${1:?"검증할 uploader.py 경로 필요"}
WORKER_SOURCE=${2:?"검증할 h264_encoder_worker.py 경로 필요"}
VIDEO_ROOT=${3:?"전체 영상 루트 필요"}
REFERENCE_A=${4:?"첫 번째 대표 영상 필요"}
REFERENCE_B=${5:?"두 번째 대표 영상 필요"}
RESULT=${6:?"결과 디렉터리 필요"}
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORK=/tmp/codex_h264_600_acceptance

for path in "$UPLOADER_SOURCE" "$WORKER_SOURCE" "$REFERENCE_A" "$REFERENCE_B"; do
  if [[ ! -f "$path" ]]; then
    echo "필수 입력 파일 없음: $path" >&2
    exit 1
  fi
done
if [[ ! -d "$VIDEO_ROOT" ]]; then
  echo "영상 루트 없음: $VIDEO_ROOT" >&2
  exit 1
fi

mapfile -t MAIN_PIDS < <(pgrep -f '^python3 main.py$')
if [[ ${#MAIN_PIDS[@]} -ne 1 ]]; then
  echo "운영 main.py PID를 하나로 확정할 수 없음: ${MAIN_PIDS[*]:-none}" >&2
  exit 1
fi
MAIN_PID=${MAIN_PIDS[0]}
MAIN_LOG=/home/hpc/drone_2026/code/logs/main.log
MAIN_FD2=$(readlink -f "/proc/$MAIN_PID/fd/2")
if [[ "$MAIN_FD2" != "$MAIN_LOG" ]]; then
  echo "main.py stderr 경로 불일치: $MAIN_FD2" >&2
  exit 1
fi
MAIN_CLIP_ENCODER=$(tr '\0' '\n' <"/proc/$MAIN_PID/environ" | sed -n 's/^CLIP_ENCODER=//p' | tail -1)
MAIN_CLIP_ENCODER=${MAIN_CLIP_ENCODER:-mp4v}
if [[ "$MAIN_CLIP_ENCODER" == "h264" ]]; then
  echo "운영 main.py가 H264 사용 중이므로 시험 중단" >&2
  exit 1
fi

mkdir -p "$WORK" "$RESULT"
cp "$UPLOADER_SOURCE" "$WORK/uploader.py"
cp "$WORKER_SOURCE" "$WORK/h264_encoder_worker.py"
cp /home/hpc/drone_2026/code/ring_buffer.py "$WORK/"
cp /home/hpc/drone_2026/code/state_store.py "$WORK/"
cp "$SCRIPT_DIR/research_h264_worker.py" "$WORK/"
cp "$SCRIPT_DIR/stage1_storage_factorial.py" "$WORK/"
cp "$SCRIPT_DIR/stage2_stability.py" "$WORK/"
cp "$SCRIPT_DIR/stage2_600_acceptance.py" "$WORK/"
python3 -m py_compile "$WORK"/*.py

{
  echo "started_at=$(date --iso-8601=seconds)"
  echo "main_pid=$MAIN_PID"
  echo "main_log=$MAIN_LOG"
  echo "main_clip_encoder=$MAIN_CLIP_ENCODER"
  echo "video_root=$VIDEO_ROOT"
  echo "reference_a=$REFERENCE_A"
  echo "reference_b=$REFERENCE_B"
  echo "bitrate=600000"
  echo "all_video_repeats=${H264_600_ALL_REPEATS:-2}"
  echo "reference_repeats=${H264_600_REFERENCE_REPEATS:-20}"
  echo "idle_sec=${H264_600_IDLE_SEC:-8.0}"
  df -B1 /dev/shm /tmp
  nvpmodel -q 2>&1 || true
} >"$RESULT/environment.txt"

tegrastats --interval 1000 >"$RESULT/tegrastats.log" 2>&1 &
TEGRA_PID=$!
cleanup() {
  kill "$TEGRA_PID" 2>/dev/null || true
  wait "$TEGRA_PID" 2>/dev/null || true
}
trap cleanup EXIT

cd "$WORK"
STAGE2_MAIN_PID="$MAIN_PID" python3 stage2_600_acceptance.py \
  "$VIDEO_ROOT" "$REFERENCE_A" "$REFERENCE_B" "$RESULT/results.jsonl" \
  | tee "$RESULT/stdout.log"
echo "finished_at=$(date --iso-8601=seconds)" >>"$RESULT/environment.txt"
