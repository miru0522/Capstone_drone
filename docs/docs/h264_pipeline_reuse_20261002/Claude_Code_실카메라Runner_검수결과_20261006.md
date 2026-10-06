ExitPlanMode가 이 세션에서 비활성화되어 있어, 검수 결과를 바로 답변으로 전달합니다.

## 판정: **APPROVED WITH CONDITIONS**

`camera_first_inference_probe.py`, `run_camera_first_inference_case.py`, `candidate_warmup/`, `candidate_preload_only/`를 읽기 전용으로 검수했습니다. **코드를 바로 고쳐야 하는 blocker는 없습니다.**

### 요청한 8개 항목 확인 결과

1. **서버 업로드/hover/주기녹화/스트리밍 차단 — OK.** probe가 `pipeline` 생성 전에 `StreamUploader.start/stop`, `PeriodicRingRecorder.start/stop`을 클래스 단위로 no-op 패치하고, `pipeline._handle_anomaly_score`를 트리거 호출 없이 score만 기록하는 람다로 덮어씀. `SERVER_URL=http://127.0.0.1:9`도 이중 안전장치.

2. **W/C 분기 — OK.** W=`uploader.warmup_clip_encoder()`(2프레임 실제 `nvv4l2h264enc` 인코딩 1회), C=`uploader.prepare_clip_encoder()`(persistent worker에 `action=prepare`만 보내 `Gst.init()`까지만 수행, NVENC 미할당)로 정확히 분리됨. prepare 경로는 이전 재검수(`Claude_Code_후보C_재검수결과_20261006.md`)에서 이미 격리 검증됨.

3. **시간축 정렬 — OK.** `mark()`가 매 이벤트에 `wall_time`/`monotonic`을 함께 남기고, tegrastats도 `time.time()`으로 0.2초 단위 타임스탬프를 찍어 같은 wall-clock 축에서 대조 가능.

4. **다른 운영 프로세스 오염 가능성 — 없음.** probe는 `start_new_session=True`로 자기만의 세션(pgid=자기 pid)을 만들고, runner의 `os.killpg`는 그 그룹에만 적용됨. persistent H264 worker는 별도 세션이라 killpg 대상에서 빠지지만, worker 자체가 `PR_SET_PDEATHSIG=SIGTERM`을 걸어 부모(probe)가 죽으면 커널이 자동으로 정리 — dae_* 등 무관 프로세스에는 애초에 영향 없음.

5. **카메라 1회 개방/정리 — OK.** `initialize_camera()`의 중복 오픈 가드 + probe `finally`에서 `stop()→release_camera()→_stop_persistent_worker()`를 각각 독립 try/except로 실행해 정상/예외 양쪽 모두 정리됨.

6. **Argus 네이티브 멈춤 — OK.** 180초 timeout → killpg(SIGTERM) → 10초 후 killpg(SIGKILL) → `sigterm_timed_out` 기록 흐름이 그대로 구현됨. SIGKILL까지 가서 probe의 `finally`가 못 돌아도 4번의 PDEATHSIG가 worker 정리를 보완.

7. **`process_snapshot()` 점유 검사 — 조건부 OK.** `"python3 main.py"` 등 정확한 문자열 매칭이 현재 운영 기동 스크립트(`start_all.sh`, `t-start_all.sh`의 `nohup python3 main.py ...`)와 일치해 지금은 오탐/누락 없음. 다만 이건 "운영 기동 방식이 바뀌지 않는다"는 가정에 의존하는 약점이고, persistent H264 worker 프로세스명은 marker에 없어 진단 snapshot(before/after)에는 잡히지 않음(PDEATHSIG로 실누수는 막히지만 가시성은 없음).

8. **W-C-C-W-W-C-C-W-W-C 순차 실행 — OK.** 스크립트가 1회 실행 후 종료하는 구조라 다음 회차는 사용자가 직접 명령을 입력해야 하며, `evidence.mkdir(..., exist_ok=False)`가 순번 재사용/덮어쓰기도 막음.

### 조건 (실행 전 지킬 것 — 이전 재검수 조건 승계 + 신규 2개)

1. (승계) 10회 카메라 반복 재시작과 SIGTERM 무응답 재발 가능성을 사용자에게 알리고 승인받은 뒤 실행.
2. (승계) 운영 main.py에는 이번 결과를 보고·승인받기 전까지 반영하지 않음. Jetson 운영 main은 중지 상태 유지.
3. (신규) 7번 항목 때문에 각 회차 직전 `ps aux | grep -E "main.py|h264_encoder_worker.py"`로 사람이 한 번 더 점유 확인.
4. (신규) 각 회차 종료 후 `runner_result.json`(returncode/sigterm_timed_out/probe_status/processes_after)과 tegrastats RAM/lfb 회복을 사람이 직접 확인하고 다음 회차로 진행 — 코드가 자동으로 다음 회차를 진행하지 않으므로 운영 절차로 지켜야 함.
