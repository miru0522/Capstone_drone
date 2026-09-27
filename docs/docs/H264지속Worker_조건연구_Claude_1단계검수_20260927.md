# H264 지속 worker 조건 연구 Claude 1단계 검수

## 최초 결과 검수

- 판정: **REVISE**
- n=20의 p95는 19번째 단일 표본이므로 방향성 수치로만 취급
- `writev`의 약 1.2% 전체 절감은 기각 가능
- 1.2Mbps만 속도·크기 후보로 진행하고 4Mbps는 품질 기준으로 유지
- 약 0.30초 잔차는 순수 IPC로 부르지 말고 상태파일 fsync, stdin, JSON,
  response fsync와 polling으로 분해할 것
- 시험 시작 시 swap 약 1.06GB 사용 사실을 후속 해석에 반영
- 장시간 반복, 품질, 실제 업로드는 비행 없는 유지보수 시간으로 제한

## IPC 진단 후 재검수

- 판정: **REVISE**
- 기존 benchmark의 `succeeded` 상태 기록 누락과 29.38% 주장 폐기가 맞음을 확인
- 약 0.30초 잔차가 `/tmp` atomic write/fsync 두 번에 의해 지배됨을 확인
- 단순 보정 22%는 미실측 가설이므로 20% 달성 판단 불가

### MUST

1. 수동 복제한 `measure_h264()` 대신 `uploader._encode_frames_h264()` 자체를 호출
2. 모듈 로드시 고정되는 `H264_STATE_PATH`를 조건마다 실제 재지정하고 사전 검증
3. 매 회차 실제 상태파일과 response 디렉터리를 결과에 기록
4. 네 조건 전환마다 swap/메모리 스냅샷 기록
5. 시험 중 운영 `main.py`의 mp4v 인코딩 트리거 중첩 여부 확인·기록

### SHOULD

- `worker_pre_encode_sec`도 결과표에 표시
- `/dev/shm` lock 파일 생성과 `flock` 직렬화 확인
- 시험 전 `/dev/shm` 여유 공간 기록
- 4조건×20회를 고정 seed로 무작위 교차

### 조건부 승인 범위

위 MUST를 반영하고 실행 전 코드 재검수를 통과하면, 동일 저장 영상의
81프레임 960x540/9fps에 대해 상태파일 위치와 response 위치의 2x2 조건을
각 20회 측정할 수 있다. 카메라·실제 업로드·전력설정 변경·maxperf·장시간
100회/30분 시험은 여전히 제외한다.

## 2x2 harness 실행 전 검수

세 차례 `REVISE`에서 다음 실행 차단 오류를 수정했다.

1. `research_h264_worker.py`가 import하는 `h264_encoder_worker.py` 복사 추가
2. 운영 로그가 연결된 stderr(fd2) 경로 검증 추가
3. PID 5563의 실제 환경에서 `CLIP_ENCODER=h264`이면 시험 중단
4. 원격 임시파일명을 암묵적으로 기대하지 않고 `SCRIPT_DIR` 기준으로 복사

최종 판정: **APPROVE**

- 운영 H264 함수 전체 경계와 `started`/`succeeded` 기록 포함 확인
- state/response 2x2 경로 라우팅과 회차별 검증 확인
- `/dev/shm` flock, 메모리/swap, main.py 로그 중첩 계측 확인
- 저장 영상 4조건×20회 무작위 교차 시험 실행 승인
