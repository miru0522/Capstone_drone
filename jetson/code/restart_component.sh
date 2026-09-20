#!/bin/bash
# 지정한 드론 Python 구성요소 하나만 PID 검증 후 안전하게 교체 기동한다.
set -eu

cd "$(dirname "$0")"

component="${1:-}"
case "$component" in
  main|command_receiver|telemetry_sender) ;;
  *) echo "usage: $0 {main|command_receiver|telemetry_sender}" >&2; exit 2 ;;
esac

mkdir -p logs
pid_file="logs/${component}.pid"
log_file="logs/${component}.log"
script_name="${component}.py"

if [ -f "$pid_file" ]; then
  old_pid="$(cat "$pid_file")"
  case "$old_pid" in
    ''|*[!0-9]*) echo "잘못된 PID 파일: $pid_file" >&2; exit 1 ;;
  esac
  if kill -0 "$old_pid" 2>/dev/null; then
    process_cwd="$(readlink -f "/proc/$old_pid/cwd" 2>/dev/null || true)"
    process_args="$(tr '\0' ' ' < "/proc/$old_pid/cmdline" 2>/dev/null || true)"
    if [ "$process_cwd" != "$(pwd -P)" ] || ! printf '%s' "$process_args" | grep -Eq "(^| )python3 ${script_name}( |$)"; then
      echo "PID $old_pid 검증 실패: cwd=$process_cwd args=$process_args" >&2
      exit 1
    fi
    kill -TERM "$old_pid"
    wait_count=0
    while kill -0 "$old_pid" 2>/dev/null && [ "$wait_count" -lt 150 ]; do
      process_state="$(ps -o stat= -p "$old_pid" 2>/dev/null || true)"
      case "$process_state" in
        Z*) break ;;
      esac
      sleep 0.1
      wait_count=$((wait_count + 1))
    done
    process_state="$(ps -o stat= -p "$old_pid" 2>/dev/null || true)"
    if kill -0 "$old_pid" 2>/dev/null && [ -n "$process_state" ]; then
      case "$process_state" in
        Z*) ;;
        *) echo "$component 종료 타임아웃: PID $old_pid" >&2; exit 1 ;;
      esac
    fi
  fi
fi

if [ -f "$log_file" ]; then
  cp "$log_file" "${log_file}.bak_$(date '+%Y%m%d_%H%M%S')"
fi

export DEVICE_KEY="${DEVICE_KEY:-HPC-2026}"
export UPLOAD_MODE="${UPLOAD_MODE:-B}"
nohup python3 "$script_name" > "$log_file" 2>&1 &
new_pid=$!
printf '%s\n' "$new_pid" > "$pid_file"
sleep 3

if ! kill -0 "$new_pid" 2>/dev/null; then
  echo "$component 시작 실패: $log_file 확인" >&2
  exit 1
fi

echo "$component 재기동 완료: PID $new_pid"
