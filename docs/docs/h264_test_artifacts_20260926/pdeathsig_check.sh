#!/usr/bin/env bash
set -eu
python3 /tmp/codex_h264_pdeathsig_smoke.py
sleep 1
child_pid="$(cat /tmp/codex_h264_pdeath_child.pid)"
state="$(ps -o stat= -p "$child_pid" 2>/dev/null || true)"
if [[ -n "$state" && "$state" != Z* ]]; then
  echo "FAIL_CHILD_ALIVE_${child_pid}"
  exit 1
fi
echo "PASS_CHILD_EXITED_${child_pid}"
