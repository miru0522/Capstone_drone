# H264 하드웨어 인코더 실기 테스트 원본

2026-09-26 Jetson `/home/hpc/drone_2026/code/`에서 읽어 보존한 원본이다.
운영 구현의 근거를 재현·검토하기 위한 자료이며 이 폴더의 파일을 운영 경로에서
직접 실행하지 않는다.

| 파일 | 용도 |
|---|---|
| `h264enctest.py` | PyGObject/GStreamer `nvv4l2h264enc` 직접 호출 구현 |
| `testermain.py` | 기존 `main.py`의 인코더만 시험 구현으로 교체한 주입 실행본 |
| `run_batch_injection.sh` | 반복 주입 시험 스크립트 |
| `run_sustained_injection.sh` | 지속 주입 시험 스크립트 |

원본 확인값:

- `h264enctest.py`: `4a898f6cc13b2f60770891ad617446eedcb24d075fa61797204944f65825376d`
- `testermain.py`: `772f87c97bb9b5292b3d7a1893e28fe4e28d7d4903d3f8a6eab9a7965fdd1af4`
