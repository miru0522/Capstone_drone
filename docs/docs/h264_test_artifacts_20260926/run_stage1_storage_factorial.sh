#!/usr/bin/env bash
set -euo pipefail

WORK=/tmp/codex_h264_stage1_factorial_b
RESULT=/tmp/codex_h264_stage1_factorial_results_b
MAIN_LOG=/home/hpc/drone_2026/code/logs/main.log
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
BASE_WORKER_SOURCE=${1:?"격리 스테이징한 h264_encoder_worker.py 경로 필요"}
UPLOADER_SOURCE=${2:?"격리 스테이징한 H264 후보 uploader.py 경로 필요"}
VIDEO=${3:?"검증할 저장 영상 경로 필요"}

if [[ ! -f "$BASE_WORKER_SOURCE" ]]; then
  echo "기본 H264 worker 스테이징 파일 없음: $BASE_WORKER_SOURCE" >&2
  exit 1
fi
if [[ ! -f "$UPLOADER_SOURCE" ]]; then
  echo "H264 후보 uploader 스테이징 파일 없음: $UPLOADER_SOURCE" >&2
  exit 1
fi
if [[ ! -f "$VIDEO" ]]; then
  echo "저장 영상 파일 없음: $VIDEO" >&2
  exit 1
fi

mkdir -p "$WORK" "$RESULT"
cp "$UPLOADER_SOURCE" "$WORK/uploader.py"
cp /home/hpc/drone_2026/code/ring_buffer.py "$WORK/"
cp /home/hpc/drone_2026/code/state_store.py "$WORK/"
cp "$BASE_WORKER_SOURCE" "$WORK/h264_encoder_worker.py"
cp "$SCRIPT_DIR/stage1_storage_factorial.py" "$WORK/stage1_storage_factorial.py"
cp "$SCRIPT_DIR/research_h264_worker.py" "$WORK/research_h264_worker.py"

python3 -m py_compile \
  "$WORK/stage1_storage_factorial.py" \
  "$WORK/research_h264_worker.py" \
  "$WORK/h264_encoder_worker.py" \
  "$WORK/uploader.py" \
  "$WORK/state_store.py" \
  "$WORK/ring_buffer.py"
MAIN_FD1=$(readlink -f /proc/5563/fd/1)
MAIN_FD2=$(readlink -f /proc/5563/fd/2)
if [[ "$MAIN_FD2" != "$MAIN_LOG" ]]; then
  echo "main.py stderr 로그 경로 불일치: fd2=$MAIN_FD2 expected=$MAIN_LOG" >&2
  exit 1
fi
MAIN_CLIP_ENCODER=$(tr '\0' '\n' </proc/5563/environ | sed -n 's/^CLIP_ENCODER=//p' | tail -1)
MAIN_CLIP_ENCODER=${MAIN_CLIP_ENCODER:-mp4v(default)}
if [[ "$MAIN_CLIP_ENCODER" == "h264" ]]; then
  echo "운영 main.py가 H264 사용 중이므로 NVENC 경합 방지를 위해 중단" >&2
  exit 1
fi
nvpmodel -q >"$RESULT/environment.txt" 2>&1 || true
{
  echo "governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"
  echo "main_pid=5563"
  echo "main_cmd=$(tr '\0' ' ' </proc/5563/cmdline)"
  echo "main_fd1=$MAIN_FD1"
  echo "main_fd2=$MAIN_FD2"
  echo "main_log_verified=$MAIN_LOG"
  echo "main_clip_encoder=$MAIN_CLIP_ENCODER"
  df -B1 /dev/shm /tmp
} >>"$RESULT/environment.txt"

tegrastats --interval 1000 >"$RESULT/tegrastats.log" 2>&1 &
TEGRA_PID=$!
cleanup() {
  kill "$TEGRA_PID" 2>/dev/null || true
  wait "$TEGRA_PID" 2>/dev/null || true
}
trap cleanup EXIT

cd "$WORK"
python3 stage1_storage_factorial.py "$VIDEO" "$RESULT/results.jsonl" | tee "$RESULT/stdout.log"
