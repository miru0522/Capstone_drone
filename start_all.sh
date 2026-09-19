#!/bin/bash
# 젯슨 부팅 후 드론 통합 파이프라인 전체 실행 스크립트.
set -eu
cd "$(dirname "$0")"

export DEVICE_KEY="${DEVICE_KEY:-HPC-2026}"

MAVSDK_SERVER_BIN="/usr/local/lib/python3.8/dist-packages/mavsdk/bin/mavsdk_server"
SERIAL_PORT="/dev/pixhawk"
GRPC_PORT="50051"

mkdir -p logs

rotate_log() {
    log_path="$1"
    if [ -f "$log_path" ]; then
        cp "$log_path" "${log_path}.bak_$(date '+%Y%m%d_%H%M%S')"
    fi
}

check_started() {
    name="$1"
    pid_file="logs/${name}.pid"
    sleep "$2"
    if ! kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo "오류: ${name} 시작 실패. logs/${name}.log 확인" >&2
        exit 1
    fi
    echo "  완료: ${name} 실행 중 (PID: $(cat "$pid_file"))"
}

echo "=================================================="
echo "드론 통합 파이프라인 시작 $(date '+%Y-%m-%d %H:%M:%S')"
echo "=================================================="

echo "[0/4] 기존 PID 검증 후 종료 중..."
./stop_all.sh

echo "[1/4] mavsdk_server 시작 ($SERIAL_PORT -> gRPC:$GRPC_PORT)"
rotate_log logs/mavsdk_server.log
nohup "$MAVSDK_SERVER_BIN" -p "$GRPC_PORT" "serial://${SERIAL_PORT}:115200" \
    > logs/mavsdk_server.log 2>&1 &
echo $! > logs/mavsdk_server.pid
check_started mavsdk_server 5

echo "[2/4] telemetry_sender.py 시작"
rotate_log logs/telemetry_sender.log
nohup python3 telemetry_sender.py > logs/telemetry_sender.log 2>&1 &
echo $! > logs/telemetry_sender.pid
check_started telemetry_sender 2

echo "[3/4] command_receiver.py 시작"
rotate_log logs/command_receiver.log
nohup python3 command_receiver.py > logs/command_receiver.log 2>&1 &
echo $! > logs/command_receiver.pid
check_started command_receiver 3

echo "[4/4] main.py 시작"
rotate_log logs/main.log
nohup python3 main.py > logs/main.log 2>&1 &
echo $! > logs/main.pid
check_started main 2

echo "=================================================="
echo "전체 실행 완료. 로그: logs/*.log"
echo "개별 재기동: ./restart_component.sh <이름>"
echo "=================================================="
