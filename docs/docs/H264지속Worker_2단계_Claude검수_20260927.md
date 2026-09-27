# H264 지속 worker 2단계 Claude 검수

## 최초 판정

**REVISE**

MUST:

1. 후보 diff를 표준 unified diff로 만들어 `git apply --check` 가능하게 할 것
2. 2단계 전 승인된 diff를 후보 소스에 반영하는 절차를 명시할 것
3. 통과·롤백 정량 기준을 시험 전에 확정할 것

## 반영 및 재검수

- `uploader_shm_candidate.diff`의 표준 hunk를 수정하고 `git apply --check` 통과
- 사용자 승인 후 후보 소스 적용, 오프라인 회귀, 격리 smoke, 장시간 시험,
  운영 배포를 서로 분리
- 지연·성공률·손상·worker 재시작·RSS/fd/thread·품질·ENOSPC·orphan 기준 추가

최종 판정: **APPROVED**

승인된 후보:

- H264 상태 기본 경로를 `H264_RAW_DIR` 아래로 이동
- persistent response를 고유한 `raw_path + ".response.json"`으로 이동
- mp4v와 per-event 경로는 변경하지 않음

승인된 2단계는 비행 없는 유지보수 시간의 mp4v/H264 각 100회·30분 반복성,
2개 이상 장면의 품질, ENOSPC·orphan·재시작 정책 시험이다. 실제 업로드 종단
지연은 3단계로 유보한다.
