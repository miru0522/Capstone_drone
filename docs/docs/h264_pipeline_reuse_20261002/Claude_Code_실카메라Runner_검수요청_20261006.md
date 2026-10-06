# Claude Code 읽기 전용 검수 요청: W/C 실카메라 1회용 runner

직전 후보 C 재검수는 `APPROVED WITH CONDITIONS`였다. 그 조건에 맞춰 실제
카메라 재시작을 수행하기 전에 실행 코드를 구체화했다. 코드 수정이나 실행은 하지
말고 읽기 전용으로 검수해 달라.

검수 파일:

- `docs/docs/h264_pipeline_reuse_20261002/camera_first_inference_probe.py`
- `docs/docs/h264_pipeline_reuse_20261002/run_camera_first_inference_case.py`
- `docs/docs/h264_pipeline_reuse_20261002/H264_GStreamer선로딩_후보C_격리검증_20261006.md`
- 조건별 후보 `candidate_warmup/`, `candidate_preload_only/`

반드시 확인할 항목:

1. probe가 실제 CSI 카메라와 VadCLIP 첫 실제 추론은 재현하면서 서버 업로드,
   threshold trigger, hover 상태 파일, 비행 명령, 주기 녹화, 스트리밍을 확실히
   차단하는가.
2. W 조건은 2프레임 실제 H264 웜업, C 조건은 GStreamer prepare만 수행하는가.
3. 첫 추론 전후 wall/monotonic 이벤트와 0.2초 tegrastats에 같은 시간축을 남겨
   RAM/lfb 변화를 대조할 수 있는가.
4. timeout → 해당 process group SIGTERM → 10초 후 SIGKILL 흐름이 다른 운영
   Python/dae 프로세스를 종료할 가능성이 없는가.
5. 한 번 실행할 때 카메라를 정확히 한 번 열고 정상/실패 양쪽에서 worker와
   카메라를 정리하는가.
6. Argus가 native call에서 멈춘 경우에도 runner가 180초 뒤 회수하고
   `sigterm_timed_out`을 증거로 남기는가.
7. `process_snapshot()`의 점유 검사에 오탐/누락이 없는가.
8. 사용자의 승인 후 W-C-C-W-W-C-C-W-W-C 순서로 한 명령씩 실행하고 각 회차
   결과와 RAM/lfb 회복을 확인한 다음 다음 회차로 넘어가도 되는가.

판정은 `APPROVED`, `APPROVED WITH CONDITIONS`, `REJECTED` 중 하나로 하고,
실카메라 실행 전에 반드시 고쳐야 할 blocker가 있으면 코드 위치와 수정안을
구체적으로 제시해 달라.
