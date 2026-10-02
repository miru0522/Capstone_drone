# Claude Code 검수 요청 프롬프트

아래 내용을 그대로 Claude Code에 전달한다.

---

`E:\univ\Capstone_drone`의 H264 웜업 + 상시 파이프라인 2차 설계와 Jetson 격리 시험 결과를 검수해줘. 이번 요청은 **검수만** 수행하고 운영 파일 수정, Jetson 카메라/main.py 재시작, 서버 전송은 하지 마.

먼저 다음 파일을 전부 읽어줘.

1. `docs/docs/h264_pipeline_reuse_20261002/H264_웜업_상시파이프라인_2차설계_20261003.md`
2. `docs/docs/h264_pipeline_reuse_20261002/검증결과_20261003.md`
3. `docs/docs/h264_pipeline_reuse_20261002/persistent_h264_pipeline_prototype.py`
4. `docs/docs/h264_pipeline_reuse_20261002/persistent_pipeline_test.py`
5. `docs/docs/h264_pipeline_reuse_20261002/baseline_worker_probe.py`
6. `docs/docs/h264_pipeline_reuse_20261002/splitmuxsink_probe.py`
7. `docs/docs/h264_pipeline_reuse_20261002/timing_probe.py`
8. `docs/docs/h264_pipeline_reuse_20261002/evidence/baseline_worker_probe_result.json`
9. `docs/docs/h264_pipeline_reuse_20261002/evidence/persistent_final_stability_result.json`
10. `docs/docs/h264_pipeline_reuse_20261002/evidence/splitmuxsink_probe_result.json`
11. `docs/docs/h264_pipeline_reuse_20261002/evidence/state_guard_smoke_result.json`
12. `docs/docs/h264_pipeline_reuse_20261002/candidate_warmup/uploader.py`
13. `docs/docs/h264_pipeline_reuse_20261002/candidate_warmup/main.py`
14. `docs/docs/h264_pipeline_reuse_20261002/warmup_candidate_unit_test.py`

비교 대상으로 다음 1차 제안과 현재 승인 worker도 읽어줘.

15. `docs/docs/h264_test_artifacts_20260926/h264_warmup_pipeline_reuse_design_20261002.md`
16. `docs/docs/h264_test_artifacts_20260926/h264_persistent_pipeline_startup_sequence_20261002.md`
17. `docs/docs/h264_600_reapply_20260930/candidate/h264_encoder_worker.py`
18. `docs/docs/h264_600_reapply_20260930/candidate/uploader.py`

다음 쟁점을 코드와 원시 JSON으로 독립 검증해줘.

- GStreamer core/splitmuxsink 1.16.3, nvv4l2h264enc 1.14.0이라는 버전 정정이 타당한가.
- 입력 전 `ASYNC_DONE`을 기다리지 않고 실제 더미 출력으로 기동을 증명해야 한다는 결론이 맞는가.
- 첫 negotiation 전 `force-IDR` 호출을 피해야 한다는 보호 로직이 충분한가.
- 지속 NVENC+appsink 구조의 20회 중앙값 8.485초와 기존 worker warm 0.928초 비교가 동일 조건이며, 상시 구조 기각 근거로 충분한가.
- splitmuxsink의 81/80/82프레임 및 마지막 조각 EOS 의존 결과가 `split-after` 사용법 오류인지, 설정으로 안전하게 해결 가능한지. 해결 가능하다고 판단하면 정확한 GStreamer 1.16.3 API 순서와 왜 지연 문제까지 개선되는지 근거를 제시해줘.
- 동적 pad relink 또는 지속 elementary stream+요청별 remux가 실제로 더 안전하고 빠른 대안인지. 단순 아이디어가 아니라 EOS, IDR/SPS/PPS, sticky event, 마지막 AU flush, mux 완결, 오류 복구를 모두 설명해줘.
- 최종 결론인 “프로세스 웜업만 별도 커밋으로 채택하고 진짜 상시 pipeline은 운영에 넣지 않는다”가 타당한가.
- 실카메라 기동 순서 비교를 이번에 실행하지 않은 것이 안전 규칙과 상시 pipeline 기각 결과에 비춰 타당한가.
- prototype에 결과 해석을 바꿀 버그, 누락된 timeout, deadlock, resource leak, 잘못된 프레임 경계 검증이 있는가.
- `candidate_warmup`의 `record_state=False` 분리가 실제 이벤트 통계 오염을 막으면서 worker 오류 복구를 훼손하지 않는가. import 위치, 시작 순서, 임시파일 정리, per_event/mp4v no-op도 확인해줘.

판정은 다음 형식으로 작성해줘.

1. `APPROVED`, `APPROVED WITH CONDITIONS`, `REJECTED` 중 하나
2. Blocker
3. 필수 수정
4. 권장 수정
5. 프로세스 웜업 운영 반영 가능 여부
6. 상시 pipeline 재검토 필요 여부와 재검토 조건

특히 원시 결과보다 추측을 우선하지 말고, 반박할 경우 재현 가능한 시험 방법과 통과 기준을 함께 제시해줘. `server/DAE-vlm-main/_codex_test2.txt`는 관계없는 파일이므로 열거나 수정하지 마.

---
