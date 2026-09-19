#!/bin/bash
# PID 파일, 작업 디렉터리, 명령행을 모두 확인한 프로세스만 종료한다.
set -eu
cd "$(dirname "$0")"

echo "드론 통합 파이프라인 종료 중..."

stop_one() {
    name="$1"
    expected="$2"
    pid_file="logs/${name}.pid"
    [ -f "$pid_file" ] || { echo "  건너뜀: ${name} PID 파일 없음"; return 0; }

    pid="$(cat "$pid_file")"
    case "$pid" in
        ''|*[!0-9]*) echo "  오류: ${name} PID 파일 형식" >&2; return 1 ;;
    esac

    if ! kill -0 "$pid" 2>/dev/null; then
        echo "  건너뜀: ${name} 이미 종료됨"
        rm -f "$pid_file"
        return 0
    fi

    process_cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    process_args="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
    if [ "$process_cwd" != "$(pwd -P)" ] || ! printf '%s' "$process_args" | grep -Eq "$expected"; then
        echo "  오류: ${name} PID 검증 실패, 종료하지 않음 (PID=$pid)" >&2
        return 1
    fi

    kill -TERM "$pid"
    count=0
    while kill -0 "$pid" 2>/dev/null && [ "$count" -lt 300 ]; do
        state="$(ps -o stat= -p "$pid" 2>/dev/null || true)"
        case "$state" in Z*) break ;; esac
        sleep 0.1
        count=$((count + 1))
    done
    state="$(ps -o stat= -p "$pid" 2>/dev/null || true)"
    if kill -0 "$pid" 2>/dev/null && [ -n "$state" ]; then
        case "$state" in
            Z*) ;;
            *) echo "  오류: ${name} 종료 타임아웃 (PID=$pid)" >&2; return 1 ;;
        esac
    fi
    rm -f "$pid_file"
    echo "  완료: ${name} 종료 (PID=$pid)"
}

stop_one main '(^| )python3 main\.py( |$)'
stop_one command_receiver '(^| )python3 command_receiver\.py( |$)'
stop_one telemetry_sender '(^| )python3 telemetry_sender\.py( |$)'
stop_one mavsdk_server 'mavsdk_server.*serial:///dev/pixhawk:115200'

echo "전체 종료 완료."
