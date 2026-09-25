"""분석 요청 관측 전용. 모델/HTTP/파일 처리 결과를 변경하지 않는다."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
import sys
import time
import traceback
import uuid

_current = ContextVar("analysis_log_context", default=None)
_instance = str(uuid.uuid4())
_dropped = 0
_model_bundle = None
_stages = ("request_body", "input", "temp_store", "videomae",
           "video_decode_preprocess", "videomae_binary", "videomae_subclass",
           "qwen", "qwen_prepare", "qwen_lock", "qwen_generate", "qwen_parse",
           "tts_auto", "metadata_merge", "submission_payload", "video_convert",
           "backend_submit", "cleanup")


@dataclass
class Context:
    analysis_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    states: dict = field(default_factory=lambda: dict.fromkeys(_stages, "not_attempted"))
    starts: dict = field(default_factory=dict)
    errors: set = field(default_factory=set)
    quality: str = "normal"
    backend_status: int | None = None


def analysis_id():
    ctx = _current.get()
    return ctx.analysis_id if ctx else None


def _json_safe(value, depth=0):
    if depth > 6:
        return None
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value[:160]
    if isinstance(value, dict):
        return {str(k)[:64]: _json_safe(v, depth + 1) for k, v in list(value.items())[:64]}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v, depth + 1) for v in value[:64]]
    return None


def emit(stage, event, level="INFO", **fields):
    """호출자는 원문/인증정보를 넘기지 않는다. 출력 장애는 업무 예외로 전파하지 않는다."""
    global _dropped
    try:
        ctx = _current.get()
        record = dict(schema_version="1.0", timestamp=datetime.now(timezone.utc).isoformat(),
                      service="ai-server", instance_id=_instance, process_id=os.getpid(),
                      model_bundle_id=_model_bundle,
                      analysis_id=ctx.analysis_id if ctx else None, event_id=None,
                      stage=stage, event=event, level=level, dropped_logs=_dropped)
        record.update(fields)
        sys.stdout.write(json.dumps(_json_safe(record), ensure_ascii=False, allow_nan=False) + "\n")
        sys.stdout.flush()
    except Exception:
        _dropped += 1


def start(stage, **fields):
    ctx = _current.get()
    if ctx:
        ctx.states[stage] = "started"
        ctx.starts[stage] = time.perf_counter()
    emit(stage, "started", **fields)


def done(stage, **fields):
    ctx = _current.get()
    if ctx:
        ctx.states[stage] = "completed"
        if stage in ctx.starts:
            fields.setdefault("duration_ms", round((time.perf_counter() - ctx.starts[stage]) * 1000, 3))
    emit(stage, "completed", **fields)


def skip(stage, reason="normal_classification"):
    ctx = _current.get()
    if ctx:
        ctx.states[stage] = "skipped"
    emit(stage, "skipped", reason_code=reason)


def degraded():
    ctx = _current.get()
    if ctx:
        ctx.quality = "degraded"


def configure_model(paths, prompt):
    """기동 시 모델 이름/파일 크기·수정시각과 프롬프트 해시를 기록. 가중치 내용 해시 아님."""
    global _model_bundle
    try:
        entries = []
        for path in paths:
            stat = os.stat(path)
            entries.append({"name": os.path.basename(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns})
        fingerprint = dict(models=entries, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
        _model_bundle = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()[:20]
        emit("model_config", "completed", **fingerprint, identity_kind="names_size_mtime_prompt")
    except Exception:
        emit("model_config", "failed", level="WARN", reason_code="identity_unavailable")


def fail(stage, exc, level="ERROR", **fields):
    ctx = _current.get()
    if ctx:
        ctx.states[stage] = "failed"
        if stage in ctx.starts:
            fields.setdefault("duration_ms", round((time.perf_counter() - ctx.starts[stage]) * 1000, 3))
    # 예외 메시지·소스 줄·locals는 입력 전문이나 인증키를 담을 수 있어 제외한다.
    error_id = id(exc)
    if ctx is None or error_id not in ctx.errors:
        fields["error_type"] = type(exc).__name__
        fields["frames"] = [{"file": os.path.basename(f.filename), "function": f.name, "line": f.lineno}
                            for f in traceback.extract_tb(exc.__traceback__)[-12:]]
        if ctx:
            ctx.errors.add(error_id)
    emit(stage, "failed", level=level, **fields)


@contextmanager
def stage(name):
    start(name)
    try:
        yield
    except BaseException as exc:
        fail(name, exc)
        raise
    else:
        done(name)


def file_info(path):
    try:
        return {"artifact_id": hashlib.sha256(os.fsencode(path)).hexdigest()[:20],
                "bytes": os.path.getsize(path) if os.path.isfile(path) else None}
    except Exception:
        return {"artifact_id": None, "bytes": None}


def snapshot(data):
    """메타데이터는 allowlist 값만 관측. 문자열·컨테이너 주입으로 원문이 새지 않게 한다."""
    try:
        if not isinstance(data, dict):
            return {"invalid_metadata_type": True}
        out = {}
        for key in ("vadScore", "score", "maeConfidence", "categoryId"):
            value = data.get(key)
            valid = type(value) in (int, float) and math.isfinite(value)
            out[key] = value if valid else None
            out[key + "_present"] = key in data
            out[key + "_invalid"] = value is not None and not valid
        label = data.get("label")
        out["label"] = label if label in ("정상", "폭력", "응급", "절도", "배회·침입") else None
        kind = data.get("type")
        out["type"] = kind if kind in ("INFO", "CRITICAL") else None
        drone = data.get("droneId")
        out["droneId"] = drone if isinstance(drone, str) and re.fullmatch(r"DR-[A-Za-z0-9_-]{1,32}", drone) else None
        for key in ("description", "ttsText"):
            value = data.get(key)
            out[key + "_length"] = len(value) if isinstance(value, str) else None
        return out
    except Exception:
        return {"snapshot_unavailable": True}


def backend_response(status):
    ctx = _current.get()
    if ctx:
        ctx.backend_status = status
    if status == 200:
        done("backend_submit", backend_http_status=status)
    else:
        if ctx:
            ctx.states["backend_submit"] = "failed"
        emit("backend_submit", "failed", level="ERROR", backend_http_status=status)


def fail_active(exc):
    ctx = _current.get()
    if ctx:
        for name in reversed(list(ctx.starts)):
            if name != "request" and ctx.states.get(name) == "started":
                fail(name, exc)


def metadata_done(before, after):
    keys = ("droneId", "label", "type", "vadScore", "score", "maeConfidence", "categoryId", "description", "ttsText")
    changed = [k for k in keys if (k in before) != (k in after) or before.get(k) != after.get(k)]
    fields = dict(before=snapshot(before), after=snapshot(after), changed_fields=changed)
    ctx = _current.get()
    if ctx and ctx.states["metadata_merge"] == "failed":
        emit("metadata_merge_summary", "completed", level="WARN", **fields)
    else:
        done("metadata_merge", **fields)


def conversion_done(converted, info):
    if converted:
        done("video_convert", output=info)
    else:
        degraded()
        ctx = _current.get()
        if ctx:
            ctx.states["video_convert"] = "failed"
        emit("video_convert", "failed", level="WARN", fallback_used=True, output=info)


class AnalysisMiddleware:
    """FastAPI 전체 바깥에 설치해 검증 오류/500 전송을 포함해 1회 종료 요약."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/analyze-video":
            return await self.app(scope, receive, send)
        ctx = Context()
        token = _current.set(ctx)
        started = time.perf_counter()
        body_bytes, status, sent, disconnected = 0, None, False, False
        unhandled_error = False
        start("request")
        start("request_body")

        async def observed_receive():
            nonlocal body_bytes, disconnected
            message = await receive()
            if message["type"] == "http.request":
                body_bytes += len(message.get("body", b""))
                if not message.get("more_body", False) and ctx.states["request_body"] == "started":
                    done("request_body", multipart_bytes=body_bytes)
            elif message["type"] == "http.disconnect":
                disconnected = True
                ctx.states["request_body"] = "failed"
            return message

        async def observed_send(message):
            nonlocal status, sent
            await send(message)
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                sent = True

        try:
            await self.app(scope, observed_receive, observed_send)
        except BaseException as exc:
            unhandled_error = True
            fail("request", exc)
            raise
        finally:
            try:
                if ctx.states["input"] == "not_attempted" and status is not None and status >= 400:
                    ctx.states["input"] = "failed"
                if ctx.states["request_body"] == "started":
                    ctx.states["request_body"] = "unknown"
                ctx.states["request"] = "completed" if not unhandled_error and sent and status is not None and status < 400 else "failed"
                emit("request_terminal", ctx.states["request"],
                     level="INFO" if ctx.states["request"] == "completed" else "ERROR",
                     response_status=status, response_sent=sent, disconnected=disconnected,
                     duration_ms=round((time.perf_counter() - started) * 1000, 3),
                     backend_http_status=ctx.backend_status,
                     backend_outcome="unknown" if ctx.states["backend_submit"] in ("started", "failed") and ctx.backend_status is None else ctx.states["backend_submit"],
                     quality=ctx.quality, stages=ctx.states)
            finally:
                _current.reset(token)
