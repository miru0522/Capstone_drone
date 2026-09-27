#!/usr/bin/env bash
set -euo pipefail

VIDEO="${1:?video path required}"
OUT="${2:?output directory required}"
mkdir -p "$OUT"

tegrastats --interval 1000 --logfile "$OUT/tegrastats.log" &
TEGRAPID=$!
cleanup() {
  kill "$TEGRAPID" 2>/dev/null || true
  wait "$TEGRAPID" 2>/dev/null || true
}
trap cleanup EXIT

timeout 120s python3 stage1_ipc_diagnostic.py \
  "$VIDEO" "$OUT/results.jsonl" | tee "$OUT/stdout.log"
