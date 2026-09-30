# H264 600 kbps 재적용 검수 번들

## 상태

- 작성·시험일: 2026-10-01
- Jetson 운영 checkout은 수정하지 않았다.
- 운영 `main.py`, 카메라, VadCLIP 프로세스는 실행하거나 재시작하지 않았다.
- 실제 서버 전송을 하지 않았다.
- P0-1~P0-5 격리 시험 완료, P0-6 실제 카메라·VadCLIP 동시 시험은 검수와 별도 승인 이후 진행한다.

## 후보 구성

`candidate/`에는 실제 반영 검토 대상 5개 파일이 있다.

- `uploader.py`, `h264_encoder_worker.py`, `start_all.sh`, `restart_component.sh`는
  `7f273bb` Git blob, 기존 manifest, 기존 candidate 파일의 SHA-256이 모두 같다.
- `main.py`는 Jetson 현재 미커밋 `PeriodicRingRecorder` 코드를 기준으로 만들었다.
- `main.py` 변경은 `CLIP_ENCODER` import와 시작 설정 로그뿐이다.
- `evidence/main_jetson_current_before_h264.py`가 병합 전 원본이다.
- 후보 구성 전후 Jetson 원본 `main.py` SHA-256은
  `f4a54398a169004a4721d4edfe8b79d26fbe082a8d1829e876ed4bbd872bf887`로 같았다.

## 격리 시험 결과

### 정적 검사

- 로컬·Jetson Python `py_compile`: 통과
- Jetson `bash -n`: 통과
- `gst-inspect-1.0 nvv4l2h264enc`: 통과
- 승인 코드 4개 SHA-256 3자 대조: 통과

### 부모 통합

입력: `/home/hpc/drone_2026/video/kakao_20260914.mp4`, 960×540, 81프레임.

| 조건 | 시간 | 크기 | 디코딩 | worker PID |
|---|---:|---:|---:|---:|
| mp4v | 2.029초 | 423,456 B | 81 | - |
| H264 cold | 2.792초 | 662,322 B | 81 | 8416 |
| H264 warm | 1.347초 | 662,322 B | 81 | 8416 |

- warm H264는 이 표본의 mp4v보다 0.682초 짧았다.
- mock HTTP에서 점수 `0.654321`은 폼에 포함됐다.
- `anomaly_score=None`은 키 자체가 빠졌다.
- `drone_id=DR-01`은 두 요청 모두 포함됐다.
- 원시 결과: `evidence/p0_parent_integration.json`

### timeout 복구

- H264 worker PID 9442가 시작된 뒤 0.8초 제한으로 timeout을 발생시켰다.
- timeout 후 `_persistent_worker` 참조와 프로세스가 정리됐다.
- 다음 15초 제한 요청은 새 PID 9450으로 1.807초에 성공했다.
- 복구 출력은 81프레임, 662,322 B였다.
- 상태는 `consecutive_failures=0`, `status=ok`로 복귀했다.
- 원시 결과: `evidence/p0_timeout_recovery.json`

### 주기 녹화 4 Mbps + 이상 클립 600 kbps 동시 인코딩

10회 모두 두 인코더를 동시에 시작했다.

| 지표 | H264 600 kbps | 주기 녹화 4 Mbps |
|---|---:|---:|
| 성공/전체 | 10/10 | 10/10 |
| 프레임 | 모두 81 | 모두 81 |
| 시간 중앙값 | 1.344초 | 1.531초 |
| 시간 최댓값 | 1.840초 | 1.869초 |
| 파일 크기 | 662,322 B | 3,967,508 B |

- persistent worker PID 8675 하나를 10회 재사용했다.
- swap은 시험 전후 0 MB 사용 상태였다.
- `/dev/shm` 가용량은 각 회차 후 원상 복구됐다.
- `MemAvailable`은 5,856,540 KiB에서 5,779,064 KiB로 변했으며 캐시 영향을 포함한다.
- 종료 후 H264 worker, 주기 녹화 worker, tegrastats, raw·partial 파일 잔재가 없었다.
- 원시 결과: `evidence/p0_concurrent_encoders.json`
- 0.2초 원시 자원 로그: `evidence/p0_concurrent_tegrastats.log`

## 검수에서 확인할 사항

1. 현재 미커밋 `PeriodicRingRecorder`가 candidate `main.py`에 온전히 보존됐는가.
2. candidate `main.py`의 추가 변경이 설정 로그 범위로 제한됐는가.
3. 승인된 H264 600 persistent worker 파일 4개의 해시 사슬이 유효한가.
4. P0 시험이 mp4v 회귀, worker 재사용, timeout 복구, 폼 데이터, 동시 NVENC 위험을 충분히 다루는가.
5. P0-6 실제 CSI 카메라·VadCLIP·H264 시험으로 넘어가는 데 차단 문제가 있는가.

## 검수 이후 단계

검수가 통과해도 바로 운영 파일을 덮어쓰지 않는다. 사용자에게 후보 diff와 P0 결과,
실제 카메라 P0-6 절차를 보고하고 승인을 받은 뒤 `main.py`만 대상으로 시험한다.
P0-6은 서버 전송, threshold 조정, hover 상태 파일, 비행 명령을 사용하지 않는다.
