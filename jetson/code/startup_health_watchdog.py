"""기동 건강성 검사 1회 시도의 네이티브 호출 timeout을 감시하는 별도 프로세스.

Python thread timeout만으로는 cuDNN/TensorRT 네이티브 호출을 취소할 수
없으므로(계속 GPU를 쥔 채 백그라운드에서 돈다), 이 watchdog은 독립
프로세스로 떠서 timeout 시 **부모(main.py) 프로세스 자체**에만 신호를
보낸다. PID 재사용을 피하기 위해 부모의 `/proc/<pid>/stat` 시작시각을
함께 확인하고, 다르면 아무 신호도 보내지 않는다.

- process group, `pkill`, `dae_*` 프로세스에는 절대 신호를 보내지 않는다.
- 정상 완료(해제 파일 생성) 시 스스로 종료한다.
- timeout 시 상태 파일에 원자적으로 기록한 뒤 SIGTERM, 유예시간 뒤
  동일 PID/시작시각일 때만 SIGKILL.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time

from state_store import update_json

POLL_INTERVAL_SEC = 0.2


def read_process_start_time(pid: int) -> float:
    """해당 PID의 실제 부팅 이후 경과 시작시각(초)을 읽는다. 없으면 OSError."""
    with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as f:
        # comm 필드에 괄호/공백이 있을 수 있어 마지막 ')' 뒤부터 분리한다.
        content = f.read()
    rparen = content.rfind(")")
    fields = content[rparen + 1 :].split()
    # stat(5): pid(1) (comm)(2) state(3) ppid(4) ... starttime은 전체 22번째
    # 필드. ")" 이후 필드 인덱스는 state가 0번이므로 starttime은 (22-3)=19.
    starttime_ticks = int(fields[19])
    clk_tck = os.sysconf("SC_CLK_TCK")
    with open("/proc/uptime", "r", encoding="utf-8") as f:
        uptime_sec = float(f.read().split()[0])
    boot_time = time.time() - uptime_sec
    return boot_time + starttime_ticks / clk_tck


def _pid_matches(pid: int, expected_start_time: float, tolerance_sec: float = 1.0) -> bool:
    try:
        actual = read_process_start_time(pid)
    except (OSError, IndexError, ValueError):
        return False
    return abs(actual - expected_start_time) <= tolerance_sec


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--start-time", type=float, required=True)
    parser.add_argument("--timeout-sec", type=float, required=True)
    parser.add_argument("--disarm-path", required=True)
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--grace-sec", type=float, default=5.0)
    args = parser.parse_args(argv)

    deadline = time.monotonic() + args.timeout_sec
    while time.monotonic() < deadline:
        if os.path.exists(args.disarm_path):
            return 0
        time.sleep(POLL_INTERVAL_SEC)

    if os.path.exists(args.disarm_path):
        return 0

    if not _pid_matches(args.pid, args.start_time):
        # PID가 이미 재사용됐거나 부모가 이미 종료됨 - 신호를 보내지 않는다.
        return 0

    def _merge_timeout(current):
        # atomic_write_json은 전체 교체라 지금까지 쌓인 attempts 기록을
        # 날린다. update_json으로 "status"와 "timeout_detail"만 얹는다 -
        # 부모가 이미 쌓아둔 상태(설정값, 이전 시도 기록)를 보존한다.
        state = dict(current or {})
        state["status"] = "timeout"
        state["timeout_detail"] = {
            "phase": args.phase,
            "attempt": args.attempt,
            "pid": args.pid,
            "timeout_sec": args.timeout_sec,
            "recorded_at": time.time(),
        }
        state["final_action"] = "abort"
        return state

    try:
        update_json(args.state_path, _merge_timeout, default={})
    except Exception:
        pass

    if not _process_alive(args.pid):
        return 0
    try:
        os.kill(args.pid, signal.SIGTERM)
    except ProcessLookupError:
        return 0

    grace_deadline = time.monotonic() + args.grace_sec
    while time.monotonic() < grace_deadline:
        if not _process_alive(args.pid):
            return 0
        time.sleep(POLL_INTERVAL_SEC)

    if _process_alive(args.pid) and _pid_matches(args.pid, args.start_time):
        try:
            os.kill(args.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
