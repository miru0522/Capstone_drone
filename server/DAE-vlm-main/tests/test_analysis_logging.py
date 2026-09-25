"""네트워크·GPU·운영 DB 없이 실제 라우트/미들웨어의 관측 계약을 검증한다."""
import asyncio
import ast
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import types
from contextlib import nullcontext
import time

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import analysis_logging as al


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


appmod = load("logging_candidate", ROOT / "app.py")


def records(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{')]


def result(category=0):
    return {"status": "ok", "result": {
        "category": ["정상", "폭력", "응급", "절도", "배회·침입"][category],
        "category_id": category, "confidence": .72, "is_anomaly": category != 0,
        "stage1": {"p_normal": .1 if category else .9, "p_anomaly": .9 if category else .1},
        "stage2": None if not category else {"probs": {"폭력": .8, "응급": .1, "절도": .05, "배회·침입": .05}},
        "scores_5class": {"정상": .1, "폭력": .72, "응급": .09, "절도": .045, "배회·침입": .045}}}


def configure(monkeypatch, tmp_path, mod=appmod, category=0, backend=200, tts_error=False, parse_error=False):
    monkeypatch.setattr(mod.tempfile, "tempdir", str(tmp_path))
    class Model:
        def predict(self, path, **kwargs):
            return copy.deepcopy(result(category))
    monkeypatch.setattr(mod, "videomae_classifier", Model())
    def vlm(*args):
        answer = "bad" if parse_error else "---SECTION_1: ADMIN_LOG---사람들이 있습니다.---END_SECTION_1---\n---SECTION_2: AUDIO_ALERT---멈추십시오.---END_SECTION_2---"
        return dict(mod._parse_vlm_sections(answer), inference_seconds=.01)
    monkeypatch.setattr(mod, "_run_vlm_inference", vlm)
    def tts(text):
        if tts_error:
            raise RuntimeError("SECRET_SENTINEL")
        p = tmp_path / "alert.wav"
        p.write_bytes(b"wav")
        return str(p)
    monkeypatch.setattr(mod, "_synthesize_tts", tts)
    def convert(path):
        target = tmp_path / "web.mp4"
        target.write_bytes(Path(path).read_bytes())
        return str(target)
    monkeypatch.setattr(mod, "_to_browser_mp4", convert)
    submitted = []
    def post(url, **kwargs):
        submitted.append(kwargs)
        if backend == "lost":
            raise ConnectionError("SECRET_SENTINEL")
        return types.SimpleNamespace(status_code=backend, text="backend result")
    monkeypatch.setattr(mod.requests, "post", post)
    return submitted


def request(mod=appmod, **data):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mod.app), base_url="http://test") as client:
            return await client.post("/analyze-video", files={"video": ("clip.mp4", b"video", "video/mp4")}, data=data)
    return asyncio.run(run())


@pytest.mark.parametrize("category", range(5))
def test_decision_and_correlation(monkeypatch, tmp_path, capsys, category):
    submitted = configure(monkeypatch, tmp_path, category=category)
    response = request(anomaly_score="0.0")
    assert response.status_code == 200
    assert response.json()["event_data"]["vadScore"] == 0.0
    logs = records(capsys)
    terminal = [r for r in logs if r["stage"] == "request_terminal"]
    assert len(terminal) == 1
    assert {r["analysis_id"] for r in logs} == {submitted[0]["headers"]["X-Analysis-Id"]}
    assert terminal[0]["stages"]["qwen"] == ("completed" if category else "skipped")
    assert terminal[0]["response_sent"]
    assert not (tmp_path / "clip.mp4").exists()
    if category:
        assert (tmp_path / "alert.wav").exists()  # 보관 정책 유지


@pytest.mark.parametrize("failure", ["tts", "lost", "http", "parse", "metadata"])
def test_partial_failure_states(monkeypatch, tmp_path, capsys, failure):
    sent = configure(monkeypatch, tmp_path, category=1, tts_error=failure == "tts",
                     backend="lost" if failure == "lost" else 401 if failure == "http" else 200,
                     parse_error=failure == "parse")
    response = request(**({"eventData": "{"} if failure == "metadata" else {}))
    logs = records(capsys)
    terminal = [r for r in logs if r["stage"] == "request_terminal"][0]
    assert "SECRET_SENTINEL" not in json.dumps(logs)
    assert terminal["stages"]["videomae"] == "completed"
    if failure == "tts":
        assert not sent
        assert terminal["stages"]["tts_auto"] == "failed"
        assert terminal["stages"]["backend_submit"] == "not_attempted"
    if failure == "lost":
        assert terminal["backend_outcome"] == "unknown"
    if failure == "http":
        assert terminal["backend_http_status"] == 401
        assert terminal["response_status"] == 500  # 기존 오류 변환 유지
    if failure in ("parse", "metadata"):
        assert terminal["quality"] == "degraded"
        assert response.status_code == 200


def test_validation_before_handler(capsys):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=appmod.app), base_url="http://test") as client:
            return await client.post("/analyze-video", data={"anomaly_score": "invalid"})
    assert asyncio.run(run()).status_code == 422
    terminal = [r for r in records(capsys) if r["stage"] == "request_terminal"][0]
    assert terminal["stages"]["input"] == "failed"
    assert terminal["stages"]["videomae"] == "not_attempted"


def test_metadata_override_does_not_leak_text(monkeypatch, tmp_path, capsys):
    configure(monkeypatch, tmp_path)
    response = request(eventData=json.dumps({"description": "SECRET_SENTINEL", "vadScore": .2, "label": "절도"}))
    assert response.json()["event_data"]["description"] == "SECRET_SENTINEL"
    logs = records(capsys)
    assert "SECRET_SENTINEL" not in json.dumps(logs)
    merge = [r for r in logs if r["stage"] == "metadata_merge" and r["event"] == "completed"][0]
    assert "description" in merge["changed_fields"]
    assert merge["before"]["label"] == "정상"
    assert merge["after"]["label"] == "절도"


def test_emit_failure_does_not_change_result(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    class Broken:
        def write(self, text):
            raise OSError("sink failure")
        def flush(self): pass
    with monkeypatch.context() as m:
        m.setattr(al.sys, "stdout", Broken())
        assert request().status_code == 200
    assert al._dropped > 0


def test_parallel_context_and_disconnect(capsys):
    ids = []
    async def inner(scope, receive, send):
        ids.append(al.analysis_id())
        await asyncio.sleep(0)
        message = await receive()
        assert message["type"] == "http.disconnect"
        assert al.analysis_id() in ids
    async def run():
        async def receive(): return {"type": "http.disconnect"}
        async def send(msg): pass
        wrapped = al.AnalysisMiddleware(inner)
        await asyncio.gather(*(wrapped({"type": "http", "path": "/analyze-video"}, receive, send) for _ in range(2)))
    asyncio.run(run())
    assert len(set(ids)) == 2
    assert al.analysis_id() is None
    terms = [r for r in records(capsys) if r["stage"] == "request_terminal"]
    assert len(terms) == 2
    assert all(r["disconnected"] and not r["response_sent"] for r in terms)


@pytest.mark.parametrize("failure", [None, "tts", "http", "parse"])
def test_matches_live_baseline(monkeypatch, tmp_path, failure):
    path = os.environ.get("BASELINE_APP")
    if not path:
        pytest.skip("BASELINE_APP must identify the pre-change source")
    baseline = load("live_baseline", Path(path))
    options = dict(category=1, tts_error=failure == "tts", backend=401 if failure == "http" else 200, parse_error=failure == "parse")
    configure(monkeypatch, tmp_path, baseline, **options)
    original = request(baseline, anomaly_score="0.3")
    configure(monkeypatch, tmp_path, appmod, **options)
    changed = request(appmod, anomaly_score="0.3")
    assert (changed.status_code, changed.json()) == (original.status_code, original.json())


@pytest.mark.parametrize("binary,sub,expected", [([.9,.1],[.8,.1,.05,.05],0),
    ([.49,.51],[.26,.25,.25,.24],1),([.1,.9],[.1,.7,.1,.1],2),
    ([.1,.9],[.1,.1,.7,.1],3),([.1,.9],[.1,.1,.1,.7],4)])
def test_actual_videomae_hierarchy_without_gpu(binary, sub, expected, capsys):
    source = ROOT.parent / "runtime_sources/videomae/videomae_infer.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "VideoMAEHierClassifier")
    predict = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "predict")
    predict.decorator_list = []
    class Scalar(int):
        def item(self): return int(self)
    class Vector(list):
        def cpu(self): return self
        def numpy(self): return self
        def argmax(self): return Scalar(max(range(len(self)), key=self.__getitem__))
    env = dict(time=time, Path=Path, nullcontext=nullcontext,
               torch=types.SimpleNamespace(softmax=lambda x, dim: [x]),
               _frames_from_mp4=lambda *args: [0] * 16,
               _preprocess=lambda *args: types.SimpleNamespace(shape=(1,3,16,224,224)),
               SCHEMA_VERSION="1.0", NUM_FRAMES=16,
               CLASS_NAMES=["정상","폭력","응급","절도","배회·침입"], SUBCLASS_NAMES=["폭력","응급","절도","배회·침입"])
    exec(compile(ast.Module(body=[predict], type_ignores=[]), str(source), "exec"), env)
    model = types.SimpleNamespace(device="cpu", binary=lambda x: Vector(binary), sub=lambda x: Vector(sub), binary_ckpt="b", sub_ckpt="s")
    token = al._current.set(al.Context())
    try:
        actual = env["predict"](model, "does-not-exist.mp4", observer=al)
    finally:
        al._current.reset(token)
    assert actual["status"] == "ok"
    assert actual["result"]["category_id"] == expected
    assert actual["result"]["confidence"] == round(binary[0] if expected == 0 else binary[1] * sub[expected-1], 4)
    logs = records(capsys)
    assert any(r["stage"] == "videomae_subclass" and r["event"] == "completed" for r in logs)


def test_cleanup_failure_and_conversion_fallback(monkeypatch, tmp_path, capsys):
    configure(monkeypatch, tmp_path)
    monkeypatch.setattr(appmod, "_to_browser_mp4", lambda p: p)
    original_remove = appmod.os.remove
    def blocked(path, *args, **kwargs):
        if str(path).endswith("clip.mp4"):
            raise OSError("SECRET_SENTINEL")
        return original_remove(path, *args, **kwargs)
    with monkeypatch.context() as context:
        context.setattr(appmod.os, "remove", blocked)
        assert request().status_code == 200
    terminal = [r for r in records(capsys) if r["stage"] == "request_terminal"][0]
    assert terminal["stages"]["cleanup"] == "failed"
    assert terminal["stages"]["video_convert"] == "failed"
    assert terminal["quality"] == "degraded"


def test_qwen_actual_helper_records_wait_and_parse(monkeypatch, capsys):
    class Inputs(dict):
        def to(self, device): return self
    class Processor:
        def apply_chat_template(self, *args, **kwargs): return "prompt"
        def __call__(self, **kwargs): return Inputs(input_ids=[[1,2]])
        def batch_decode(self, *args, **kwargs):
            return ["---SECTION_1: ADMIN_LOG---내용---END_SECTION_1---"]
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False), no_grad=nullcontext))
    monkeypatch.setitem(sys.modules, "qwen_vl_utils", types.SimpleNamespace(process_vision_info=lambda m: (None, [0])))
    monkeypatch.setattr(appmod, "vlm_processor", Processor())
    monkeypatch.setattr(appmod, "vlm_model", types.SimpleNamespace(generate=lambda **kw: [[1,2,3]]))
    token = al._current.set(al.Context())
    try:
        out = appmod._run_vlm_inference("test.mp4", "폭력")
        assert out["audio_alert"]
        assert al._current.get().quality == "degraded"
    finally:
        al._current.reset(token)
    logs = records(capsys)
    assert any(r["stage"] == "qwen_lock" and r["event"] == "completed" and r["duration_ms"] >= 0 for r in logs)
    assert any(r["stage"] == "qwen_parse_quality" and r["fallback_used"] for r in logs)


def test_exception_after_response_is_not_success(capsys):
    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b"ok"})
        raise RuntimeError("SECRET_SENTINEL")
    async def run():
        async def receive(): return {"type": "http.request", "body": b""}
        async def send(message): pass
        await al.AnalysisMiddleware(inner)({"type": "http", "path": "/analyze-video"}, receive, send)
    with pytest.raises(RuntimeError):
        asyncio.run(run())
    terminal = [r for r in records(capsys) if r["stage"] == "request_terminal"]
    assert len(terminal) == 1
    assert terminal[0]["event"] == "failed"
    assert terminal[0]["response_sent"]
    assert al.analysis_id() is None
