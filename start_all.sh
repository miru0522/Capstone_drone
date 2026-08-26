#!/bin/bash
# start_all.sh
# 젯슨 부팅 후 드론 통합 파이프라인 전체 실행 스크립트
#
# 실행 순서:
#   1. mavsdk_server (시리얼 포트 독점, gRPC 50051 오픈)
#   2. telemetry_sender.py (위치/배터리 서버 전송)
#   3. command_receiver.py (STOMP 명령 수신 + 드론 제어)
#   4. main.py (카메라+추론+호버링)
#
# 로그는 각각 logs/*.log 로 분리 저장. PID는 logs/*.pid 에 저장.
# 종료는 stop_all.sh 사용.

set -e
cd "$(dirname "$0")"

MAVSDK_SERVER_BIN="/usr/local/lib/python3.8/dist-packages/mavsdk/bin/mavsdk_server"
SERIAL_PORT="/dev/pixhawk"
GRPC_PORT="50051"

mkdir -p logs

echo "=================================================="
echo " 드론 통합 파이프라인 시작 $(date '+%Y-%m-%d %H:%M:%S')"
echo "=================================================="

# ── 0. 기존 실행중인 프로세스 정리 ─────────────────────
echo "[0/4] 기존 프로세스 정리 중..."
pkill -f "mavsdk_server" 2>/dev/null || true
pkill -f "telemetry_sender.py" 2>/dev/null || true
pkill -f "command_receiver.py" 2>/dev/null || true
pkill -f "main.py" 2>/dev/null || true
sleep 2

# ── 1. mavsdk_server 시작 (시리얼 포트 독점) ────────────
echo "[1/4] mavsdk_server 시작 중... ($SERIAL_PORT -> gRPC:$GRPC_PORT)"
nohup "$MAVSDK_SERVER_BIN" -p "$GRPC_PORT" "serial://${SERIAL_PORT}:115200" \
    > logs/mavsdk_server.log 2>&1 &
echo $! > logs/mavsdk_server.pid
sleep 5   # Pixhawk 디스커버리 대기

if ! kill -0 "$(cat logs/mavsdk_server.pid)" 2>/dev/null; then
    echo "❌ mavsdk_server 시작 실패! logs/mavsdk_server.log 확인 필요"
    exit 1
fi
echo "    ✅ mavsdk_server 실행 중 (PID: $(cat logs/mavsdk_server.pid))"

# ── 2. telemetry_sender.py ──────────────────────────────
echo "[2/4] telemetry_sender.py 시작 중..."
nohup python3 telemetry_sender.py > logs/telemetry_sender.log 2>&1 &
echo $! > logs/telemetry_sender.pid
sleep 2
echo "    ✅ telemetry_sender 실행 중 (PID: $(cat logs/telemetry_sender.pid))"

# ── 3. command_receiver.py ──────────────────────────────
echo "[3/4] command_receiver.py 시작 중..."
nohup python3 command_receiver.py > logs/command_receiver.log 2>&1 &
echo $! > logs/command_receiver.pid
sleep 3
echo "    ✅ command_receiver 실행 중 (PID: $(cat logs/command_receiver.pid))"

# ── 4. main.py (카메라+추론+호버링) ─────────────────────
echo "[4/4] main.py 시작 중..."
nohup python3 main.py > logs/main.log 2>&1 &
echo $! > logs/main.pid
sleep 2
echo "    ✅ main.py 실행 중 (PID: $(cat logs/main.pid))"

echo "=================================================="
echo " 전체 실행 완료. 로그 확인: tail -f logs/*.log"
echo " 종료하려면: ./stop_all.sh"
echo "=================================================="
