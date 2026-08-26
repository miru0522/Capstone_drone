#!/bin/bash
# t-start_all.sh
# 배터리(또는 GPS) 미인식 상태에서 테스트용 텔레메트리로 전체 파이프라인 실행
#
# 사용법:
#   ./t-start_all.sh <모드>
#   모드: 1=가짜GPS만, 2=가짜배터리만, 3=가짜GPS+가짜배터리
#
# 예시:
#   ./t-start_all.sh 3
#
# 실행 순서:
#   1. mavsdk_server (시리얼 포트 독점, gRPC 50051 오픈)
#   2. test_telemetry_sender.py <모드> (테스트용 위치/배터리 서버 전송)
#   3. command_receiver.py (STOMP 명령 수신 + 드론 제어)
#   4. main.py (카메라+추론+호버링)
#
# 로그는 각각 logs/*.log 로 분리 저장. PID는 logs/*.pid 에 저장.
# 종료는 stop_all.sh 사용 (공통).

set -e
cd "$(dirname "$0")"

MODE="$1"
if [[ "$MODE" != "1" && "$MODE" != "2" && "$MODE" != "3" ]]; then
    echo "사용법: $0 <모드>"
    echo "  모드 1: 가짜 GPS만 (배터리는 실제값)"
    echo "  모드 2: 가짜 배터리만 (GPS는 실제값)"
    echo "  모드 3: 가짜 GPS + 가짜 배터리 둘 다"
    exit 1
fi

MAVSDK_SERVER_BIN="/usr/local/lib/python3.8/dist-packages/mavsdk/bin/mavsdk_server"
SERIAL_PORT="/dev/pixhawk"
GRPC_PORT="50051"

mkdir -p logs

echo "=================================================="
echo " [TEST 모드=$MODE] 드론 통합 파이프라인 시작 $(date '+%Y-%m-%d %H:%M:%S')"
echo " ⚠️  테스트 전용 실행입니다. 실제 운용에는 사용하지 마세요."
echo "=================================================="

# ── 0. 기존 실행중인 프로세스 정리 ─────────────────────
echo "[0/4] 기존 프로세스 정리 중..."
pkill -f "mavsdk_server" 2>/dev/null || true
pkill -f "telemetry_sender.py" 2>/dev/null || true
pkill -f "test_telemetry_sender.py" 2>/dev/null || true
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

# ── 2. test_telemetry_sender.py <모드> ──────────────────
echo "[2/4] test_telemetry_sender.py (모드=$MODE) 시작 중..."
nohup python3 test_telemetry_sender.py "$MODE" > logs/test_telemetry_sender.log 2>&1 &
echo $! > logs/test_telemetry_sender.pid
sleep 2
echo "    ✅ test_telemetry_sender 실행 중 (PID: $(cat logs/test_telemetry_sender.pid))"

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
echo " [TEST 모드=$MODE] 전체 실행 완료. 로그 확인: tail -f logs/*.log"
echo " 종료하려면: ./stop_all.sh"
echo "=================================================="
