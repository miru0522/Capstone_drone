# H264 지속 worker 1단계 IPC 세부 진단

## 범위

- 운영 파일과 카메라를 변경하지 않은 Jetson `/tmp` 격리 시험
- 저장 영상에서 만든 960x540 BGR 81프레임, 9fps
- H264 1.2Mbps 지속 worker 20회
- `main.py` PID 5563이 실행 중인 상태의 선별 계측

## 결과

| 구간 | p50 | p95 | max |
|---|---:|---:|---:|
| `started` 상태 기록 | 149.59ms | 157.31ms | 160.75ms |
| JSON 직렬화 | 0.175ms | 0.211ms | 0.329ms |
| stdin write/flush | 0.056ms | 0.101ms | 0.169ms |
| stdin에서 worker read | 0.114ms | 0.306ms | 37.40ms |
| worker JSON parse | 0.134ms | 0.147ms | 0.201ms |
| worker pre-encode | 0.0046ms | 0.0052ms | 0.0052ms |
| worker encode | 815.63ms | 952.68ms | 1298.55ms |
| response fsync/replace/poll | 148.77ms | 151.55ms | 155.62ms |
| 상태 기록 시작부터 response 감지 | 1111.83ms | 1248.25ms | 1645.32ms |

기존에 약 0.30초로 묶었던 잔차의 대부분은 실제 stdin IPC나 JSON 처리가
아니라 ext4 `/tmp`에 수행한 두 번의 atomic JSON 기록이다. `started` 상태 기록과
response 기록이 각각 약 0.15초를 차지했다. 첫 회의 stdin-to-read 37.40ms는 cold
이상치이며 이후 p95는 0.306ms다.

## 측정 누락 발견

기존 `stage1_condition_benchmark.py`의 `measure_h264()`는 운영 경로를 수동으로
분해하면서 마지막 `_record_h264_state("succeeded", ...)` 호출을 빠뜨렸다. 실제
`uploader._encode_frames_h264()`는 반환 전에 이 기록을 수행한다. 따라서 기존
H264 p95 1.420초와 29.38% 단축 주장은 운영 함수 경계보다 약 0.15초 낮게
측정되었을 가능성이 크며, 수정 실험 전에는 채택 근거로 사용하지 않는다.

단순 보정값을 더하면 H264 p95는 약 1.57초, mp4v 대비 약 22% 단축이지만 이는
실측값이 아니다. 다음 시험은 반드시 `started`와 `succeeded` 기록을 모두 포함한
생산 함수 경계에서 다시 측정한다.

## 다음 검수 안건

1. `/tmp` 상태파일과 `/tmp` response를 그대로 둔 수정 기준선
2. H264 전용 상태파일만 `/dev/shm`으로 옮긴 조건
3. worker response만 `/dev/shm`으로 옮긴 조건
4. 둘 다 `/dev/shm`으로 옮긴 조건

각 조건은 연구 harness에서만 20회 무작위 교차 측정한다. 이 2x2 요인 시험을
실행하기 전에 Claude가 측정 경계, 내구성 의미, 안전 조건을 검수한다.
