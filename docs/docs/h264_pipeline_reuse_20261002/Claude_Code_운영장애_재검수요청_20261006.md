# Claude Code 운영 장애 재검수 요청

`E:\univ\Capstone_drone`의 H264 600 + 프로세스 웜업 운영 반영 직후 Jetson에서 Argus `InsufficientMemory`가 재현됐다. 사용자 지침에 따라 임의 롤백이나 재시작 전에 원인과 다음 조치를 검수해줘. 운영 파일을 수정하거나 Jetson 프로세스를 시작하지 말고 읽기·분석만 수행해줘.

## 적용 내용

- Jetson checkout: `/home/hpc/drone_2026/code`, branch `vadclip-v4-20260831`
- 기본 H264 600 커밋: `0fcbd0d Enable H264 600 kbps clip encoding`
- 웜업 커밋: `5728ae1 Warm H264 clip encoder before inference loop`
- 실제 working tree `main.py`에는 기존 미커밋 `PeriodicRingRecorder` 257줄이 별도로 유지돼 있다. 두 커밋에는 포함하지 않았다.
- 적용 전 main 프로세스는 실행 중이지 않았다.
- 실행 전 `tegrastats`: RAM 1578/6833MB, lfb 248x4MB, SWAP 103/3417MB.
- 기존 P0-6에서 같은 유형의 Argus `InsufficientMemory`가 3회 중 1회 발생한 전례가 있다.

## 실제 기동 타임라인

원시 로그: `docs/docs/h264_pipeline_reuse_20261002/evidence/operational_main_argus_failure_20261005.log`

1. 18:38:06 main 시작, `UPLOAD_MODE=B`, `encoder=h264`
2. 18:38:07 CSI 카메라 초기화와 첫 프레임 성공
3. 18:39:26 VadCLIP/TensorRT 초기화 완료
4. 18:39:34 VadCLIP warmup 완료
5. 18:39:34 H264 persistent worker PID 39006 시작
6. 18:39:37 H264 더미 2프레임 웜업 성공: 2.562초, 6037 bytes
7. 18:39:37 캡처/추론/PeriodicRingRecorder 감시 루프 시작
8. 18:39:44 첫 VadCLIP 실추론 성공: 596ms
9. 18:39:45 이후 Argus `NvMapMemAllocInternalTagged error 12`, `InsufficientMemory`, `IImageNativeBuffer not supported` 발생
10. 로그는 18:39:46 이후 완전히 멈췄지만 main PID는 다음날까지 생존했다.
11. 다음날 확인: main RSS 4,721,256 KiB, RAM 4935/6833MB, lfb 24x1MB. H264 worker RSS 55,320 KiB.
12. SIGTERM으로 종료되지 않아 로그 보존 후 main PID만 SIGKILL했다. worker는 PDEATHSIG로 함께 종료됐다.
13. 종료 후 RAM 926/6833MB, lfb 246x4MB로 회복했다.

## 별도 smoke

main 기동 전에 운영 `uploader.py`의 `warmup_clip_encoder(960,540,9)`만 별도 프로세스에서 실행했을 때는 성공했고, `/dev/shm/drone_clip_encoder_state.json`은 실행 전후 모두 존재하지 않아 이벤트 통계 비오염도 확인했다.

## 검수할 파일

1. `docs/docs/h264_pipeline_reuse_20261002/candidate_warmup/uploader.py`
2. `docs/docs/h264_pipeline_reuse_20261002/candidate_warmup/main.py`
3. `docs/docs/h264_pipeline_reuse_20261002/evidence/operational_main_argus_failure_20261005.log`
4. `docs/docs/h264_pipeline_reuse_20261002/evidence/p0` 파일이 아니라, 과거 비교 근거는 `docs/docs/h264_600_reapply_20260930/evidence/p0_live_*`
5. `docs/docs/h264_pipeline_reuse_20261002/H264_웜업_상시파이프라인_2차설계_20261003.md`

## 질문

1. 이번 실패를 H264 웜업이 유발했다고 볼 근거가 충분한가, 아니면 기존 Argus 단편화의 비결정적 재발로 봐야 하는가.
2. `카메라 -> VadCLIP -> H264 웜업` 순서가 카메라가 이미 streaming 중인 상태에서 NVMM/NVENC 할당을 추가해 Argus 연속 메모리를 깨뜨릴 수 있는가.
3. 다음 후보 중 무엇이 가장 안전한가.
   - A: 프로세스 웜업 제거, 기본 H264 600만 사용
   - B: `카메라 -> H264 웜업 -> VadCLIP` 순서로 이동
   - C: H264 worker 프로세스만 미리 spawn하고 실제 2프레임 encode는 하지 않음
   - D: 다른 방안
4. 재시험한다면 연속 재시작을 피하면서 어떤 회수, 순서, RAM/lfb 기준, 관찰 시간을 써야 하는가.
5. 현재 두 커밋은 유지하고 실행만 중단할지, 웜업 커밋만 revert할지, 코드 수정 후보를 먼저 만들지 판정해줘.

## 요구 판정 형식

1. `APPROVED`, `APPROVED WITH CONDITIONS`, `REJECTED` 중 하나
2. 원인 판정과 확신도
3. 즉시 조치
4. 다음 코드 후보
5. 재시험 절차와 중단 기준
6. 사용자 승인 요청 전에 준비할 자료

`server/DAE-vlm-main/_codex_test2.txt`, 다른 Python 프로세스, `dae_*`는 관계없으므로 건드리지 마.
