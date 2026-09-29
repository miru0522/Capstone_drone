# H264 600 kbps 교체 준비 (2026-09-29)

## 준비 상태

운영 Jetson은 아직 mp4v로 동작한다. 이 디렉터리는 H264 600 kbps 교체에 필요한 현재 운영 기준본, 배포 후보, 사전 점검 스크립트와 품질 결과를 모은 검토용 번들이다. **운영 파일 복사와 `main.py` 재시작은 수행하지 않았다.**

현재 운영 checkout을 읽기 전용으로 확인한 결과는 다음과 같다.

- 브랜치/HEAD: `vadclip-v4-20260831`, `f1fade2`
- 운영 `main.py`: PID `5563`, `UPLOAD_MODE=B`, `CLIP_ENCODER` 미지정으로 기본 mp4v
- 운영 `uploader.py`: H264 경로가 없는 이전 버전
- 운영 `h264_encoder_worker.py`: 파일 없음
- 운영 tracked 파일 변경: 없음. 기존 백업·시험 파일은 untracked로 존재

따라서 환경변수만 바꾸면 시작 단계에서 실패한다. `candidate/uploader.py`와 `candidate/h264_encoder_worker.py`를 함께 반영하고 시작 스크립트에 아래 값을 넣어야 한다.

```bash
export CLIP_ENCODER="${CLIP_ENCODER:-h264}"
export H264_BITRATE="${H264_BITRATE:-600000}"
```

## 채택 근거

지연시간 합격 기준은 고정 참조 영상과 전체 집계의 p50·p95가 mp4v보다 각각 0.1초 이상 짧은 것이다.

| 범위 | p50 단축 | p95 단축 |
|---|---:|---:|
| 전체 100회 | 0.426초 | 0.739초 |
| 참조 A | 0.264초 | 0.278초 |
| 참조 B | 0.463초 | 0.408초 |

- 인코딩/디코딩 안정성: 200/200 성공, 모두 81프레임
- persistent worker: 단일 PID 재사용
- H264 장시간 p95 변화: +1.30%
- 서버 VideoMAE 판정: 기존 시험에서 600 kbps 포함 검증 완료
- `maxperf-enable=true`: 0.1초 기준 달성에 필요하지 않아 후보에서 제외

## 픽셀 품질

2026-09-29 `/home/hpc/drone_2026/video`의 30개 영상에서 동일한 81개 원본 프레임을 mp4v와 H264 600 kbps로 각각 한 번 인코딩해 비교했다.

| 지표 | mp4v | H264 600 kbps |
|---|---:|---:|
| 영상 평균 PSNR의 전체 평균 | 37.02 dB | 36.36 dB |
| 최저 영상 평균 PSNR | 33.93 dB | 32.00 dB |
| PSNR 30 dB 이상 영상 | 30/30 | 30/30 |
| 영상 평균 SSIM의 전체 평균 | 0.96820 | 0.95575 |
| SSIM 0.95 이상 영상 | 27/30 | 23/30 |
| 평균 파일 크기 | 1,255,478 bytes | 682,161 bytes |

집계 PSNR 30 dB, SSIM 0.95 기준은 H264 600 kbps가 통과한다. mp4v 대비 평균 변화는 PSNR -0.666 dB, SSIM -0.01245이고 파일 크기는 45.67% 감소했다. 영상별 SSIM 편차는 있으므로 교체 후 초기 실제 트리거 영상에서 화질과 서버 판정을 관찰한다.

## 파일 구성

- `baseline/`: 2026-09-29 운영 Jetson에서 가져온 변경 전 파일
- `candidate/`: H264 지원 uploader, worker, H264 600 kbps 기본값을 넣은 시작 스크립트
- `quality_results/results.jsonl`: 30영상 × 2코덱 프레임 품질 원시 결과
- `quality_results/analysis.json`: 품질 요약과 mp4v 대비 변화
- `cutover_preflight.sh`: 운영 변경 없이 후보 문법·플러그인·현재 PID를 확인

## 실제 교체 순서

1. 운영 로그와 Git 상태를 다시 보존한다.
2. `cutover_preflight.sh`를 Jetson의 격리 디렉터리에서 실행한다.
3. 운영 `uploader.py`, `start_all.sh`, `restart_component.sh`를 시각이 포함된 이름으로 백업한다.
4. 후보 `uploader.py`, `h264_encoder_worker.py`, 두 시작 스크립트를 운영 checkout에 복사한다.
5. `py_compile`, `bash -n`, `git diff --check`를 실행한다.
6. 변경분을 `vadclip-v4-20260831`에 커밋하고 원격 브랜치에 push한다.
7. `./restart_component.sh main`으로 `main.py`만 재시작한다. `start_all.sh` 전체 재기동과 `pkill python3`은 사용하지 않는다.
8. 새 PID 환경에서 `CLIP_ENCODER=h264`, `H264_BITRATE=600000`, `UPLOAD_MODE=B`를 확인한다.
9. 시작 로그와 첫 실제 트리거 한 건에서 H264 인코딩 완료, 업로드 성공, 서버 수신·판정을 확인한다.

롤백은 백업 파일을 복원하고 `CLIP_ENCODER=mp4v ./restart_component.sh main`으로 `main.py`만 재시작한다. 교체 실행은 별도 승인 단계에서 수행한다.
