# Claude Code 재검수 요청: H264 후보 C(GStreamer 선로딩만 수행)

읽기 전용 검수를 요청합니다. 코드 수정, 운영 반영, 프로세스 기동, 커밋, revert는
하지 마세요.

## 배경

직전 검수에서 2026-10-05 운영 Argus `InsufficientMemory`와 과거 P0-6 run2의
동일 오류를 대조한 뒤 다음과 같이 판정했습니다.

- 2프레임 H264 웜업은 실패의 필수 원인이 아니다.
- 실제 NVENC/NVMM 할당이 메모리 여유를 줄였을 가능성은 배제할 수 없다.
- 운영 main은 중지하고 기존 두 커밋은 보존한다.
- 우선 후보는 worker/GStreamer만 선로딩하고 실제 encode는 트리거까지 미루는 C다.

직전 판정 원문:
`docs/docs/h264_pipeline_reuse_20261002/Claude_Code_운영장애_1차판정_20261006.md`

## 검수 대상

1. 결과 문서:
   `docs/docs/h264_pipeline_reuse_20261002/H264_GStreamer선로딩_후보C_격리검증_20261006.md`
2. 후보 코드:
   - `candidate_preload_only/h264_encoder_worker.py`
   - `candidate_preload_only/uploader.py`
   - `candidate_preload_only/main.py`
3. 시험 코드:
   - `preload_only_unit_test.py`
   - `preload_only_jetson_probe.py`
   - `preload_then_encode_jetson_probe.py`
4. 비교 기준:
   - `candidate_warmup/`
   - `../h264_600_reapply_20260930/candidate/`
5. 운영 장애 로그:
   `evidence/operational_main_argus_failure_20261005.log`

## 확인 요청

1. `action=prepare`가 실제로 GStreamer import/init만 하고 NVENC pipeline을 만들지
   않는지 코드 수준에서 확인해 주세요.
2. 기존 action 없는 encode 요청과 호환되는지, persistent worker lock·timeout·종료
   처리에 회귀가 없는지 확인해 주세요.
3. `prepare_clip_encoder()`가 H264 상태 통계를 변경하거나 임시 파일을 남길 수 있는
   경로가 있는지 확인해 주세요.
4. prepare 실패 후 첫 실제 encode에서 정상 재시도할 수 있는지 확인해 주세요.
5. 보고서의 Jetson 격리 증거가 주장 범위를 충분히 뒷받침하는지 확인해 주세요.
6. 보고서 6절의 실카메라 조건 W 5회 + 조건 C 5회 비교가 안전하고 원인 분리에
   충분한지 확인해 주세요. 시험 횟수·순서·중단 기준을 바꿔야 하면 구체적으로
   제안해 주세요.
7. 후보 C를 실카메라 비교 시험에 올려도 되는지를 최종 판정해 주세요.

## 판정 형식

- `APPROVED`, `APPROVED WITH CONDITIONS`, `REJECTED` 중 하나
- Blocker와 필수 수정 사항
- 사용자 승인이 필요한 다음 시험의 정확한 범위
- 운영 반영 가능 여부와 아직 금지해야 할 범위
