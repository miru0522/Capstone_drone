#!/bin/bash
# stop_all.sh - 통합 파이프라인 전체 종료
cd "$(dirname "$0")"

echo "드론 통합 파이프라인 종료 중..."

for name in main command_receiver telemetry_sender mavsdk_server; do
    if [ -f "logs/${name}.pid" ]; then
        pid=$(cat "logs/${name}.pid")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            echo "  ✅ ${name} 종료 (PID: $pid)"
        else
            echo "  ⚠️  ${name} 이미 종료됨"
        fi
        rm -f "logs/${name}.pid"
    fi
done

# 혹시 남은 프로세스 강제 정리
pkill -f "mavsdk_server" 2>/dev/null || true
pkill -f "telemetry_sender.py" 2>/dev/null || true
pkill -f "command_receiver.py" 2>/dev/null || true
pkill -f "main.py" 2>/dev/null || true

echo "전체 종료 완료."
