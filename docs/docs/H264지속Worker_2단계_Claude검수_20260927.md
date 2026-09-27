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

## 후보 적용 후 3단계 코드 검수

- 개발 PC 구문·오프라인 회귀: PASS
- 기본 state 경로, persistent response 위치·고유성·cleanup 테스트 추가
- mp4v/per-event 경로 변경 없음

판정: **APPROVED**

REJECT: none

MUST: none

## Jetson 파일시스템 확인 후 4단계 위험 검수

실측 결과 `/tmp`는 ext4, `/dev/shm`은 3.3GiB tmpfs였다. 기존 `/tmp` state와
달리 후보 state는 재부팅 시 소실되지만, 연속 실패 값은 자동 롤백이 아닌 경보용
보조 지표이고 영속 main 로그를 1차 증거로 쓰는 정책이므로 후보는 유지한다.

판정: **APPROVED**

MUST:

1. main 로그의 실제 영속 경로 확인
2. ENOSPC와 재시작 후 상태 정책 실기기 검증
3. 종료 후 orphan 0개 실증

1번은 운영 PID 5563의 stdout/stderr가 ext4의
`/home/hpc/drone_2026/code/logs/main.log`을 가리키는 것으로 확인했다. 2·3번은
비행 없는 유지보수 시간의 장시간 2단계 시험에서 수행한다.
