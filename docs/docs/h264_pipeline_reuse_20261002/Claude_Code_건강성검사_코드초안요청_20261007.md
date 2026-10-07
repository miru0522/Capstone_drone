# Claude Code 요청: H264 W + VadCLIP 기동 건강성 검사 코드 초안

E:\univ\Capstone_drone에서 H264 W 구조 뒤에 VadCLIP 기동 건강성 검사를
추가하는 코드 초안을 작성해줘.

이번 작업은 로컬 후보 코드와 카메라 없는 격리 시험까지만 승인한다. Jetson 운영
checkout 수정, CSI 카메라 실행, main.py 재기동, 서버 전송, commit, push는 하지 마.

## 먼저 읽을 파일

- `docs/docs/h264_pipeline_reuse_20261002/H264_W_VadCLIP_기동건강성검사_설계_20261007.md`
- `docs/docs/h264_pipeline_reuse_20261002/H264_W대C_실카메라비교결과_20261006.md`
- `docs/docs/h264_pipeline_reuse_20261002/Claude_Code_실카메라Runner_검수결과_20261006.md`
- `docs/docs/h264_pipeline_reuse_20261002/candidate_warmup/main.py`
- `docs/docs/h264_pipeline_reuse_20261002/candidate_warmup/uploader.py`
- `docs/docs/h264_pipeline_reuse_20261002/candidate_warmup/h264_encoder_worker.py`
- `jetson/code/anomaly_model_trt.py`
- `jetson/code/vadclip_adapter_trt.py`
- `docs/md/CLAUDE.md`
- `E:\univ\AGENTS.md`

## 목표

W 방식은 유지한다.

- persistent H264 worker 기동
- 검은 프레임 2장을 실제 `nvv4l2h264enc`로 인코딩
- 첫 실제 트리거가 warm 인코딩 경로 사용

그 직후 실제 CSI 프레임 기반 VadCLIP 건강성 검사를 실행할 수 있는 후보 코드를
작성한다.

건강성 검사는 다음을 보장해야 한다.

- 실제 `score=0.0`과 추론 예외를 코드와 로그에서 명확히 구분
- `detect_anomaly()`의 0.0 폴백을 사용하지 않음
- score 값이 아니라 예외 없이 유한한 점수를 반환했는지로 성공 판정
- 성공·실패 모두 VadCLIP feature history 정리
- H264 상태에서 최대 3회 재시도
- 3회 실패하거나 H264 웜업이 실패하면 H264 worker를 종료하고 mp4v로 전환
- mp4v 상태에서 최대 2회 재검증
- mp4v에서 성공하면 `degraded_mp4v`로 운영 루프 진입 허용
- mp4v에서도 실패하면 `startup_failed`로 운영 루프 진입 금지
- timeout이면 같은 프로세스를 정상 상태로 계속 사용하지 않음
- 자동 재시작 루프를 추가하지 않음

## 구현 위치

새 디렉터리를 만들어:

`docs/docs/h264_pipeline_reuse_20261002/candidate_startup_health/`

기존 `candidate_warmup/` 파일은 수정하지 말고 새 디렉터리로 복사한 뒤 작업해.

최소 후보 파일:

- `main.py`
- `uploader.py`
- `h264_encoder_worker.py`
- `anomaly_model_trt.py`
- `vadclip_adapter_trt.py`
- 필요하면 `startup_health.py`
- 필요하면 `startup_health_watchdog.py`

테스트와 결과 문서는 다음에 작성해:

- `docs/docs/h264_pipeline_reuse_20261002/startup_health_unit_test.py`
- `docs/docs/h264_pipeline_reuse_20261002/startup_health_timeout_probe.py`
- `docs/docs/h264_pipeline_reuse_20261002/H264_W_VadCLIP_건강성검사_초안결과_20261007.md`

## 구현 요구사항

### 1. 구조화된 결과

건강성 검사 결과가 최소한 다음 정보를 가져야 한다.

```python
{
    "ok": bool,
    "score": float | None,
    "phase": "h264_active" | "mp4v_fallback",
    "attempt": int,
    "elapsed_ms": float,
    "error_type": str | None,
    "error_message": str | None,
    "memory_before": dict | None,
    "memory_after": dict | None,
}
```

정상적인 0점:

```python
{"ok": True, "score": 0.0}
```

추론 예외:

```python
{"ok": False, "score": None, "error_type": "..."}
```

### 2. 프레임 입력

운영 후보에서는 카메라에서 `INFER_WINDOW_LEN`개의 새 프레임을 수집해 검사하도록
구현하되, 이번 로컬 단위 시험에서는 카메라를 열지 않도록 frame provider를 주입
가능하게 만들어.

예:

```python
run_startup_healthcheck(
    anomaly_pipeline,
    frame_provider,
    ...
)
```

검사 프레임은 다음 경로에 전달하지 마.

- ring buffer
- upload queue
- threshold 판정
- hover 상태 파일
- 비행 명령
- periodic recorder
- StreamUploader

### 3. 재시도 설정

기본값:

```text
VADCLIP_HEALTHCHECK_MAX_ATTEMPTS=3
VADCLIP_HEALTHCHECK_BACKOFF_SEC=2.0
VADCLIP_FALLBACK_HEALTHCHECK_ATTEMPTS=2
VADCLIP_HEALTHCHECK_TIMEOUT_SEC=20
```

설정 검증:

- 최대 시도 횟수는 1~5
- backoff는 0 이상
- timeout은 양수
- 각 시도는 새 frame window 사용

### 4. feature history 정리

건강성 검사가 성공하거나 예외가 발생해도 feature buffer가 운영 추론에 남지 않게
해.

`vadclip_adapter_trt.py`에 공개적인 `reset_history()` 또는 동등한 API를 추가하는
방식을 우선 검토해.

기존 `warmup()`도 compute 도중 실패하면 history가 남을 수 있으므로 `try/finally`
정리가 필요한지 확인하고 반영해.

### 5. 런타임 인코더 폴백

현재 `CLIP_ENCODER`는 import 시 결정되므로 환경변수만 나중에 변경하는 방식은
금지한다.

`uploader.py`에 명시적인 active encoder 개념을 추가해.

예상 인터페이스:

```python
get_active_clip_encoder() -> str
activate_mp4v_fallback(reason: str) -> None
```

조건:

- configured encoder와 active encoder 구분
- 폴백 시 persistent H264 worker 종료
- 이후 `encode_frames_to_mp4()`는 mp4v 경로 사용
- 같은 이벤트에서 H264 실패 후 mp4v 재인코딩하는 로직 추가 금지
- 폴백은 운영 루프 진입 전에만 허용
- thread-safe 전환
- configured/active/reason 로그 기록
- main.py는 import 시 복사된 `CLIP_ENCODER` 대신 실제 active encoder 조회

### 6. 상태 파일

기본 경로:

`/tmp/drone_startup_health.json`

환경변수:

`STARTUP_HEALTH_STATE_PATH`

기존 `atomic_write_json()`을 사용하고 다음 상태를 지원해.

- `checking`
- `healthy_h264`
- `healthy_h264_recovered`
- `degraded_mp4v`
- `startup_failed`
- `timeout`

상태 파일 필드:

- schema_version
- pid
- configured_encoder
- active_encoder
- h264_warmup_ok
- started_at
- completed_at
- attempts
- final_action
- fallback_reason

### 7. 로그와 메모리

각 시도 전후에 구조화된 로그 마커를 남겨.

```text
vadclip_healthcheck_start phase=... attempt=...
vadclip_healthcheck_pass phase=... attempt=...
vadclip_healthcheck_failed phase=... attempt=...
vadclip_healthcheck_timeout phase=... attempt=...
```

cuDNN 예외는 type/message/traceback을 기록해.

NvMap은 네이티브 stderr이므로 직접 가로채지 말고 start/end 로그 마커 사이의 시간
범위로 연결되게 해.

메모리 sampler는 주입 가능하게 구현해. 운영 후보 기본 sampler는 tegrastats 한
줄에서 다음을 파싱해.

- RAM used/total
- SWAP used/total
- lfb count
- lfb block size

sampler 실패만으로 건강성 검사를 실패시키지 말고 `memory_sample_error`를 기록해.

### 8. timeout

Python thread timeout만 걸고 네이티브 호출을 계속 살려두는 방식은 금지한다.

설계 문서의 watchdog 방향을 비판적으로 검토해서 안전한 초안을 작성해. 운영
프로세스에 실제 SIGKILL을 보내는 시험은 이번 단계에서 하지 마.

watchdog 조건:

- parent PID와 `/proc/<pid>/stat` 시작 시각 확인
- 정상 완료 시 해제
- timeout 상태 파일 원자 기록
- 해당 parent PID에만 SIGTERM
- 유예시간 뒤 동일 PID와 시작 시각일 때만 SIGKILL
- process group, `pkill`, `dae_*`에 신호 금지
- watchdog 자체 잔존 금지

단위 시험에서는 signal sender를 주입하거나 무해한 별도 child process를 사용해
현재 작업 프로세스를 죽이지 마.

watchdog 방식이 과도하거나 더 위험하다고 판단하면 더 안전한 대안을 구현해도
된다. 그 경우 변경 이유와 trade-off를 결과 문서에 기록해.

### 9. main 기동 gate

후보 `main.py` 순서:

```text
카메라 open
→ 기존 VadCLIP warmup
→ H264 W warmup
→ 실제 프레임 건강성 검사
→ 최종 active encoder 및 health 상태 확인
→ 성공 또는 degraded_mp4v일 때만 pipeline.run()
```

다음 상태에서는 `pipeline.run()`을 호출하지 마.

- `startup_failed`
- `timeout`
- 유효하지 않은 health result

H264 warmup 실패도 조용히 무시하지 말고 mp4v 폴백 건강성 검사로 연결해.

실패 경로에서 카메라와 H264 worker를 정리해.

## 카메라 없는 필수 시험

다음 단위 시험을 작성하고 실행해.

1. 정상 score 반환 → `healthy_h264`
2. 정상 score=0.0 → `ok=true`, `healthy_h264`
3. 첫 시도 cuDNN 예외, 두 번째 성공 → `healthy_h264_recovered`
4. H264 상태 3회 실패, mp4v 첫 시도 성공
   - H264 worker stop 호출
   - active encoder mp4v
   - `degraded_mp4v`
   - 운영 loop 진입 허용
5. H264 3회와 mp4v 2회 모두 실패
   - `startup_failed`
   - 운영 loop 진입 금지
6. H264 warmup 자체 실패 후 mp4v 건강성 성공
7. frame provider 실패
8. memory sampler 실패
9. feature history가 성공·실패 양쪽에서 비워지는지
10. timeout watchdog 정상 해제
11. timeout 시 대상 child PID만 종료하는지
12. PID 시작 시각 불일치 시 신호를 보내지 않는지
13. 각 최종 상태 파일 schema 확인
14. mp4v/per-event 기존 경로에 불필요한 H264 warmup이 없는지

실제 CSI 카메라, 서버, hover, 비행 명령은 사용하지 마.

## 검증

- 수정한 모든 Python 파일 `py_compile`
- 단위 시험 실행
- 기존 W 후보와 diff 검토
- H264 encode 경로 자체가 불필요하게 바뀌지 않았는지 확인
- `candidate_warmup/` 원본과 운영 파일이 수정되지 않았는지 확인
- `server/DAE-vlm-main/_codex_test2.txt`는 건드리지 마
- `PeriodicRingRecorder` 코드와 미커밋 변경 보존

## 결과 보고서

다음 문서를 작성해:

`docs/docs/h264_pipeline_reuse_20261002/H264_W_VadCLIP_건강성검사_초안결과_20261007.md`

포함 내용:

- 실제 구현 구조
- 설계 문서에서 변경한 판단과 이유
- 파일별 diff 요약
- 테스트별 PASS/FAIL
- timeout 구현의 안전 범위와 한계
- 아직 실카메라에서 검증되지 않은 항목
- 운영 반영 금지 범위
- 다음 Claude Code 재검수에 필요한 파일 목록
- 사용자 승인 후 수행할 실카메라 P0의 정확한 범위

작업 완료 후 코드와 시험 결과를 한 번에 보고하고 대기해. commit, push, Jetson
복사, 운영 반영은 하지 마.
