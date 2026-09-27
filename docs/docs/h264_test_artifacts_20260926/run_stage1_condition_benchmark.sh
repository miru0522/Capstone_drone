#!/usr/bin/env bash
set -euo pipefail

VIDEO="${1:?video path required}"
OUT="${2:?output directory required}"
mkdir -p "$OUT"

{
  date --iso-8601=seconds
  nvpmodel -q || true
  cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || true
  cat /sys/devices/17000000.gv11b/devfreq/17000000.gv11b/cur_freq 2>/dev/null || true
  free -m
} > "$OUT/environment.txt" 2>&1

tegrastats --interval 1000 --logfile "$OUT/tegrastats.log" &
TEGRAPID=$!
cleanup() {
  kill "$TEGRAPID" 2>/dev/null || true
  wait "$TEGRAPID" 2>/dev/null || true
}
trap cleanup EXIT

timeout 300s python3 stage1_condition_benchmark.py \
  "$VIDEO" "$OUT/results.jsonl" | tee "$OUT/stdout.log"
