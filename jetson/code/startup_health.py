"""H264 W 웜업 직후 VadCLIP 기동 건강성 검사.

detect_anomaly()의 운영 중 0.0 폴백은 쓰지 않는다 — 실제 score=0.0과
추론 예외를 구조적으로 구분해야 2026-10-06 W/C 비교 5회차처럼 "probe는
PASS인데 추론은 실패"한 상황을 놓치지 않는다.

성공 판정은 score 값이 아니라 "예외 없이 유한한 0.0~1.0 score를
반환했는가"로만 내린다.
"""

from __future__ import annotations

import dataclasses
import logging
import math
import numbers
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from state_store import atomic_write_json

logger = logging.getLogger("startup_health")

# ─── 설정값 ──────────────────────────────────────────────────────
MAX_ATTEMPTS_H264 = int(os.environ.get("VADCLIP_HEALTHCHECK_MAX_ATTEMPTS", "3"))
BACKOFF_SEC = float(os.environ.get("VADCLIP_HEALTHCHECK_BACKOFF_SEC", "2.0"))
MAX_ATTEMPTS_MP4V = int(os.environ.get("VADCLIP_FALLBACK_HEALTHCHECK_ATTEMPTS", "2"))
TIMEOUT_SEC = float(os.environ.get("VADCLIP_HEALTHCHECK_TIMEOUT_SEC", "20"))
STATE_PATH = os.environ.get("STARTUP_HEALTH_STATE_PATH", "/tmp/drone_startup_health.json")

if not 1 <= MAX_ATTEMPTS_H264 <= 5:
    raise ValueError(
        f"VADCLIP_HEALTHCHECK_MAX_ATTEMPTS는 1..5 범위여야 함: {MAX_ATTEMPTS_H264}"
    )
if not 1 <= MAX_ATTEMPTS_MP4V <= 5:
    raise ValueError(
        f"VADCLIP_FALLBACK_HEALTHCHECK_ATTEMPTS는 1..5 범위여야 함: {MAX_ATTEMPTS_MP4V}"
    )
if BACKOFF_SEC < 0:
    raise ValueError(f"VADCLIP_HEALTHCHECK_BACKOFF_SEC는 0 이상이어야 함: {BACKOFF_SEC}")
if TIMEOUT_SEC <= 0:
    raise ValueError(f"VADCLIP_HEALTHCHECK_TIMEOUT_SEC는 양수여야 함: {TIMEOUT_SEC}")

_WATCHDOG_PATH = str(Path(__file__).with_name("startup_health_watchdog.py"))

_TEGRASTATS_RAM = re.compile(r"RAM (\d+)/(\d+)MB")
_TEGRASTATS_SWAP = re.compile(r"SWAP (\d+)/(\d+)MB")
_TEGRASTATS_LFB = re.compile(r"lfb (\d+)x(\d+)(kB|MB)")


@dataclass
class HealthAttemptResult:
    ok: bool
    score: Optional[float]
    phase: str
    attempt: int
    elapsed_ms: float
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    memory_before: Optional[dict] = None
    memory_after: Optional[dict] = None
    memory_sample_error: Optional[str] = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _reap_tegrastats(proc: subprocess.Popen, grace_sec: float = 1.0) -> None:
    """tegrastats는 계속 실행되는 상시 프로세스다 — 자식 잔존을 막기 위해
    terminate -> wait, 실패하면 해당 PID만 kill -> wait로 반드시 회수한다."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=grace_sec)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        proc.kill()
        proc.wait(timeout=grace_sec)
    except subprocess.TimeoutExpired:
        logger.error("tegrastats 샘플러 자식 프로세스 회수 실패: pid=%s", proc.pid)


def _parse_tegrastats_memory(line: str) -> Dict[str, Any]:
    """tegrastats RAM/SWAP/lfb를 MB 기준으로 정규화한다.

    Xavier NX의 lfb block 단위는 메모리 상태에 따라 ``MB``뿐 아니라
    ``kB``로도 출력된다. 예를 들어 ``28x512kB``를 파싱 실패로 버리면
    연속 메모리가 가장 부족한 구간의 진단값이 누락되므로 1024진 MB로
    변환해 같은 ``lfb_block_mb`` 필드에 기록한다.
    """
    ram = _TEGRASTATS_RAM.search(line)
    swap = _TEGRASTATS_SWAP.search(line)
    lfb = _TEGRASTATS_LFB.search(line)
    if not (ram and swap and lfb):
        raise RuntimeError(f"tegrastats_parse_failed: {line!r}")

    lfb_value = int(lfb.group(2))
    lfb_unit = lfb.group(3)
    lfb_block_mb = lfb_value if lfb_unit == "MB" else lfb_value / 1024.0

    return {
        "ram_used_mb": int(ram.group(1)),
        "ram_total_mb": int(ram.group(2)),
        "swap_used_mb": int(swap.group(1)),
        "lfb_count": int(lfb.group(1)),
        "lfb_block_mb": lfb_block_mb,
    }


def default_memory_sampler(timeout_sec: float = 3.0) -> Dict[str, Any]:
    """tegrastats 첫 유효 행 한 줄에서 RAM/SWAP/lfb를 파싱한다.

    tegrastats는 `--interval`로 지정한 주기마다 계속 출력하는 상시
    프로세스라 `subprocess.run(timeout=...)`로 기다리면 정상 Jetson에서도
    항상 timeout이 난다(2026-10-07 초안의 실제 버그 — Codex 검수로 발견).
    Popen으로 첫 줄만 읽고 즉시 종료시킨다.

    실패해도 건강성 검사 자체를 실패시키지 않는다 — 호출부가
    memory_sample_error로만 기록한다. 시작 실패/첫 행 timeout/파싱 실패를
    서로 구분해서 예외 메시지에 남긴다.
    """
    import select

    try:
        proc = subprocess.Popen(
            ["tegrastats", "--interval", "200"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        raise RuntimeError(f"tegrastats_start_failed: {exc}") from exc

    line: Optional[str] = None
    try:
        deadline = time.monotonic() + timeout_sec
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("tegrastats_first_line_timeout")
            ready, _, _ = select.select([proc.stdout], [], [], remaining)
            if not ready:
                raise RuntimeError("tegrastats_first_line_timeout")
            raw = proc.stdout.readline()
            if not raw:
                raise RuntimeError("tegrastats_closed_before_output")
            raw = raw.strip()
            if raw:
                line = raw
                break
    finally:
        _reap_tegrastats(proc)

    return _parse_tegrastats_memory(line)


def _safe_sample(sampler: Optional[Callable[[], Dict[str, Any]]]) -> tuple:
    if sampler is None:
        return None, None
    try:
        return sampler(), None
    except Exception as exc:  # noqa: BLE001 - 자원 샘플링 실패는 검사 실패가 아님
        return None, f"{type(exc).__name__}: {exc}"


class _Watchdog:
    """건강성 검사 1회 시도를 감시하는 독립 프로세스 핸들."""

    def __init__(self, phase: str, attempt: int, timeout_sec: float, state_path: str):
        self.phase = phase
        self.attempt = attempt
        self.timeout_sec = timeout_sec
        self.state_path = state_path
        self.disarm_fd, self.disarm_path = tempfile.mkstemp(
            prefix="startup_health_disarm_", suffix=".flag"
        )
        os.close(self.disarm_fd)
        os.remove(self.disarm_path)  # 파일이 "생기는 것"이 해제 신호
        self.pid = os.getpid()
        self.start_time = self._read_own_start_time()
        self.process: Optional[subprocess.Popen] = None

    @staticmethod
    def _read_own_start_time() -> float:
        from startup_health_watchdog import read_process_start_time

        return read_process_start_time(os.getpid())

    def arm(self) -> None:
        popen_kwargs: Dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        self.process = subprocess.Popen(
            [
                sys.executable, _WATCHDOG_PATH,
                "--pid", str(self.pid),
                "--start-time", repr(self.start_time),
                "--timeout-sec", str(self.timeout_sec),
                "--disarm-path", self.disarm_path,
                "--state-path", self.state_path,
                "--phase", self.phase,
                "--attempt", str(self.attempt),
            ],
            **popen_kwargs,
        )

    def disarm_and_join(self, join_timeout_sec: float = 3.0) -> None:
        try:
            Path(self.disarm_path).touch()
        except OSError:
            pass
        if self.process is None:
            return
        try:
            self.process.wait(timeout=join_timeout_sec)
        except subprocess.TimeoutExpired:
            logger.warning(
                "startup_health watchdog pid=%s가 해제 후에도 종료되지 않음 - 강제 종료",
                self.process.pid,
            )
            try:
                self.process.terminate()
                self.process.wait(timeout=2.0)
            except Exception:
                logger.exception("watchdog 강제 종료 실패")
        finally:
            try:
                os.remove(self.disarm_path)
            except OSError:
                pass


def run_healthcheck_attempt(
    anomaly_pipeline,
    frame_provider: Callable[[], Any],
    phase: str,
    attempt: int,
    *,
    memory_sampler: Optional[Callable[[], Dict[str, Any]]] = default_memory_sampler,
    timeout_sec: float = TIMEOUT_SEC,
    state_path: str = STATE_PATH,
) -> HealthAttemptResult:
    """건강성 검사 1회 시도. 성공/실패와 무관하게 feature history를 정리한다."""

    memory_before, mem_before_err = _safe_sample(memory_sampler)

    watchdog = _Watchdog(phase, attempt, timeout_sec, state_path)
    watchdog.arm()

    logger.info("vadclip_healthcheck_start phase=%s attempt=%d", phase, attempt)
    started = time.monotonic()
    ok = False
    score: Optional[float] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    try:
        window = frame_provider()
        score = anomaly_pipeline.compute_score(window)
        # 성공 계약: 예외 없이 반환된 유한한 0.0~1.0 실수만 성공이다.
        # bool은 Python에서 int의 하위클래스라 isinstance(True, (int,float))가
        # True가 되므로 명시적으로 배제한다(Codex 검수로 발견).
        if isinstance(score, bool) or not isinstance(score, numbers.Real):
            raise RuntimeError(f"VadCLIP score가 숫자가 아님: {score!r}")
        score = float(score)
        if not math.isfinite(score):
            raise RuntimeError(f"VadCLIP score가 유한하지 않음(NaN/Inf): {score!r}")
        if not (0.0 <= score <= 1.0):
            raise RuntimeError(f"VadCLIP score가 0.0~1.0 범위 밖임: {score!r}")
        ok = True
    except Exception as exc:  # noqa: BLE001 - 모든 예외를 구조화해서 기록해야 함
        error_type = type(exc).__name__
        error_message = str(exc)
        score = None
    finally:
        try:
            anomaly_pipeline.reset_history()
        except Exception:
            logger.exception(
                "건강성 검사 후 feature history 초기화 실패(phase=%s attempt=%d)",
                phase, attempt,
            )
        watchdog.disarm_and_join()

    elapsed_ms = (time.monotonic() - started) * 1000.0
    memory_after, mem_after_err = _safe_sample(memory_sampler)
    memory_sample_error = mem_before_err or mem_after_err

    if ok:
        logger.info(
            "vadclip_healthcheck_pass phase=%s attempt=%d score=%.6f elapsed_ms=%.1f",
            phase, attempt, score, elapsed_ms,
        )
    else:
        logger.error(
            "vadclip_healthcheck_failed phase=%s attempt=%d error_type=%s "
            "elapsed_ms=%.1f error=%s",
            phase, attempt, error_type, elapsed_ms, error_message,
        )

    return HealthAttemptResult(
        ok=ok,
        score=score,
        phase=phase,
        attempt=attempt,
        elapsed_ms=elapsed_ms,
        error_type=error_type,
        error_message=error_message,
        memory_before=memory_before,
        memory_after=memory_after,
        memory_sample_error=memory_sample_error,
    )


def run_startup_health_gate(
    anomaly_pipeline,
    frame_provider: Callable[[], Any],
    uploader_module,
    *,
    h264_warmup_ok: bool,
    memory_sampler: Optional[Callable[[], Dict[str, Any]]] = default_memory_sampler,
    state_path: str = STATE_PATH,
) -> dict:
    """H264(있다면) -> mp4v 순서로 건강성 검사를 수행하고 최종 상태를 반환한다.

    반환값의 "final_action"이 "pipeline_run"이 아니면 호출자는 추론 루프를
    시작하면 안 된다.
    """

    state: Dict[str, Any] = {
        "schema_version": 1,
        "status": "checking",
        "pid": os.getpid(),
        "configured_encoder": uploader_module.CLIP_ENCODER,
        "active_encoder": uploader_module.get_active_clip_encoder(),
        "h264_warmup_ok": h264_warmup_ok,
        "started_at": time.time(),
        "attempts": [],
        "final_action": None,
        "fallback_reason": None,
    }
    atomic_write_json(state_path, state)

    attempts: List[HealthAttemptResult] = []

    def _record(result: HealthAttemptResult) -> None:
        attempts.append(result)
        state["attempts"] = [a.to_dict() for a in attempts]
        atomic_write_json(state_path, state)

    final_status: Optional[str] = None
    fallback_reason: Optional[str] = None

    attempt_h264 = h264_warmup_ok and uploader_module.get_active_clip_encoder() == "h264"
    if attempt_h264:
        for attempt in range(1, MAX_ATTEMPTS_H264 + 1):
            result = run_healthcheck_attempt(
                anomaly_pipeline, frame_provider, "h264_active", attempt,
                memory_sampler=memory_sampler, state_path=state_path,
            )
            _record(result)
            if result.ok:
                final_status = "healthy_h264" if attempt == 1 else "healthy_h264_recovered"
                break
            if attempt < MAX_ATTEMPTS_H264:
                time.sleep(BACKOFF_SEC)
        if final_status is None:
            fallback_reason = "h264_healthcheck_exhausted"
    elif uploader_module.get_active_clip_encoder() == "h264":
        # active=h264인데 웜업 자체가 실패한 경우 - h264 건강성 검사를
        # 시도하지 않고 바로 mp4v로 넘어간다.
        fallback_reason = "h264_warmup_failed"
    else:
        fallback_reason = "h264_not_configured"

    if final_status is None:
        if uploader_module.get_active_clip_encoder() == "h264":
            try:
                uploader_module.activate_mp4v_fallback(fallback_reason or "unknown")
            except Exception as exc:
                # worker 종료를 확인할 수 없으면 mp4v가 정말 안전한지 알 수
                # 없다 - "거짓 정상"으로 넘어가지 않고 즉시 기동 실패로
                # 처리한다(2026-10-07 Codex 검수로 추가된 계약).
                state["status"] = "startup_failed"
                state["final_action"] = "abort"
                state["fallback_reason"] = fallback_reason
                state["worker_shutdown_error"] = f"{type(exc).__name__}: {exc}"
                state["completed_at"] = time.time()
                atomic_write_json(state_path, state)
                logger.critical(
                    "H264 worker 종료 확인 실패로 기동 실패 처리: %s", exc,
                )
                return state
        state["active_encoder"] = uploader_module.get_active_clip_encoder()
        state["fallback_reason"] = fallback_reason
        atomic_write_json(state_path, state)

        for attempt in range(1, MAX_ATTEMPTS_MP4V + 1):
            result = run_healthcheck_attempt(
                anomaly_pipeline, frame_provider, "mp4v_fallback", attempt,
                memory_sampler=memory_sampler, state_path=state_path,
            )
            _record(result)
            if result.ok:
                final_status = "degraded_mp4v"
                break
            if attempt < MAX_ATTEMPTS_MP4V:
                time.sleep(BACKOFF_SEC)
        if final_status is None:
            final_status = "startup_failed"

    final_action = (
        "pipeline_run"
        if final_status in ("healthy_h264", "healthy_h264_recovered", "degraded_mp4v")
        else "abort"
    )

    state["status"] = final_status
    state["active_encoder"] = uploader_module.get_active_clip_encoder()
    state["final_action"] = final_action
    state["fallback_reason"] = fallback_reason
    state["completed_at"] = time.time()
    atomic_write_json(state_path, state)

    logger.info(
        "startup_health_gate_done status=%s active_encoder=%s final_action=%s "
        "fallback_reason=%s attempts=%d",
        final_status, state["active_encoder"], final_action, fallback_reason, len(attempts),
    )

    return state
