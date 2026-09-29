# H264 600 kbps 교체 준비 번들 (2026-09-29)

## 상태와 범위

운영 Jetson은 아직 mp4v로 동작한다. 이 디렉터리는 H264 600 kbps 교체에 필요한 운영 기준본, 배포 후보, 해시, 사전 검사와 시험 근거를 모은 검토용 번들이다. 운영 파일 복사와 `main.py` 재시작은 수행하지 않았다.

- 운영 브랜치/HEAD: `vadclip-v4-20260831`, `f1fade2`
- 운영 `main.py`: PID `5563`, `UPLOAD_MODE=B`, `CLIP_ENCODER` 미설정이므로 mp4v
- 운영 `uploader.py`: H264 경로가 없는 이전 버전
- 운영 `h264_encoder_worker.py`: 없음
- 교체 후보: `main.py`, `uploader.py`, `h264_encoder_worker.py`, `start_all.sh`, `restart_component.sh`
- 시작 설정: `CLIP_ENCODER=h264`, `H264_BITRATE=600000`
- `maxperf-enable=true`: 후보에서 제외

`candidate/main.py`는 운영 기준본에 인코더 설정 로그만 추가한 파일이다. H264 기능은 `candidate/uploader.py`와 `candidate/h264_encoder_worker.py`에 있다.

## 채택 근거

합격 기준은 인코딩 구간 p50·p95가 고정 참조 영상별로 mp4v보다 각각 0.1초 이상 짧은 것이다.

| 범위 | p50 단축 | p95 단축 |
|---|---:|---:|
| 전체 100회 | 0.426초 | 0.739초 |
| 참조 A | 0.264초 | 0.278초 |
| 참조 B | 0.463초 | 0.408초 |

- 인코딩·디코딩 성공: 200/200, 결과당 81프레임
- persistent worker: 단일 PID 재사용
- H264 장시간 p95 변화: +1.30%
- 평균 파일 크기: mp4v 대비 45.67% 감소

이 결론은 인코딩 구간에 한정한다. 서버 수신과 추론을 포함한 종단 지연은 통제된 대조 측정이 없으므로 개선을 주장하지 않는다.

## 픽셀 품질

동일한 960×540 원본 프레임 81개를 전체 30영상에서 각 코덱으로 인코딩·디코딩해 비교했다.

| 지표 | mp4v | H264 600 kbps |
|---|---:|---:|
| 전체 평균 PSNR | 37.02 dB | 36.36 dB |
| 최저 영상 평균 PSNR | 33.93 dB | 32.00 dB |
| 영상 평균 PSNR 30 dB 이상 | 30/30 | 30/30 |
| 전체 평균 SSIM | 0.96820 | 0.95575 |
| 영상 평균 SSIM 0.95 이상 | 27/30 | 23/30 |
| 평균 파일 크기 | 1,255,478 bytes | 682,161 bytes |

전체 평균 PSNR 30 dB와 SSIM 0.95 기준은 통과했다. 시험 프로그램의 영상별 전건 gate는 mp4v와 H264 모두 false였으며, 입력별 SSIM 편차는 초기 운영 관찰 항목이다.

## 서버 판정 근거의 한계

기존 서버 원시 자료를 다시 집계한 결과 mp4v와 H264 600 kbps 직접 짝 비교는 **28/30**이다.

- `Assault006_x264.mp4`: H264 요청이 180초 ReadTimeout으로 끝났지만 동일 내용·동일 원본 크기의 중복 파일에서는 성공했다.
- `Burglary017_x264.mp4`: H264 요청이 180초 ReadTimeout으로 끝났고 대체 결과가 없다.
- `Abuse028_x264.mp4`: 두 조건 모두 `CRITICAL`이지만 categoryId가 mp4v 1에서 H264 2로 바뀌었다.

따라서 서버 VideoMAE 판정을 30/30 검증 완료로 표현하지 않는다. 원시 JSONL, traceback, 정정 분석은 `../h264_test_artifacts_20260926/codex_quality_allvideo_results/`에 있다. 서버 재전송은 수행하지 않았다.

## 파일 구성

- `baseline/`: 2026-09-29 운영 Jetson에서 가져온 변경 전 기준 파일
- `candidate/`: 검토할 전체 교체 후보 5개
- `manifest.json`: LF 바이트 기준 SHA-256과 실행 설정
- `quality_results/`: 30영상 픽셀 품질 원시 결과와 분석
- `cutover_preflight.sh`: 후보 문법·의존성·잔존 프로세스·공유 메모리·PID·해시 검사
- `preflight_result.txt`: Jetson 격리 디렉터리에서 실행한 원본 출력

`.gitattributes`가 관련 Python·shell 파일을 LF로 고정한다. manifest와 preflight 해시는 실제 Jetson에 올릴 LF 파일을 기준으로 한다.

## 승인 후 교체 순서

1. 운영 로그, Git 상태, PID와 환경을 다시 기록한다.
2. 번들을 Jetson 격리 디렉터리에 올리고 `cutover_preflight.sh`를 실행한다.
3. manifest 해시와 Jetson 격리 사본의 `sha256sum`을 대조한다.
4. 운영 후보 5개 파일을 각각 시간 표시 이름으로 백업한다. 운영에 없는 worker는 없음 상태를 기록한다.
5. 후보 5개 파일을 운영 checkout에 복사하고 `py_compile`, `bash -n`, `git diff --check`를 수행한다.
6. **먼저** `CLIP_ENCODER=mp4v ./restart_component.sh main`을 실행한다. 새 PID, 설정 로그, 기존 mp4v 동작을 확인해 실제 롤백 경로를 실증한다.
7. 6단계가 통과한 경우에만 변경분을 `vadclip-v4-20260831`에 커밋·push한다.
8. `./restart_component.sh main`으로 main만 다시 시작해 H264 600 kbps를 활성화한다.
9. 새 PID 환경에서 `CLIP_ENCODER=h264`, `H264_BITRATE=600000`, `UPLOAD_MODE=B`를 확인한다.
10. 별도 승인된 첫 실제 트리거에서 H264 인코딩, 업로드와 서버 결과를 확인한다.

`start_all.sh` 전체 재기동, `pkill python3`, `dae_*` 조작은 하지 않는다. 6단계의 실제 재시작과 이후 활성화는 운영 변경이므로 별도 승인 전에는 실행하지 않는다.

## 중단 및 롤백 조건

- preflight 실패, 해시 불일치, 잔존 worker 또는 `/dev/shm` 상태 파일 발견
- `logs/main.pid`와 실제 PID 불일치
- mp4v 확인 재시작에서 기존 동작과 차이 발생
- H264 새 PID 환경변수 불일치
- H264 인코딩 실패, 3초 초과, 업로드 실패
- 상태 파일의 `rollback_recommended=true`

중단 시 백업 파일을 복원하고 `CLIP_ENCODER=mp4v ./restart_component.sh main`으로 main만 재시작한다. `rollback_recommended`는 자동 조치 신호가 아니며 운영자가 로그를 확인한 뒤 이 절차를 실행한다.

첫 H264 요청은 worker 기동 비용으로 최대 1.758초가 관측됐다. 이벤트당 약 120 MiB의 `/dev/shm` 원시 프레임을 사용하므로 배포 직전 `free -m`과 `df -B1 /dev/shm`을 확인하고, worker 로그 증가량도 초기 운영에서 관찰한다.
