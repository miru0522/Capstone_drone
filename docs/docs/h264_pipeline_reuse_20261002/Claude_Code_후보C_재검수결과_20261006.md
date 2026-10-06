# Claude Code 후보 C 재검수 결과 (2026-10-06)

## 판정: APPROVED WITH CONDITIONS

코드(`h264_encoder_worker.py`, `uploader.py`, `main.py`), 시험 스크립트 3종,
승인된 H264 600 baseline과의 diff, 운영 장애 로그를 대조했다.

## 확인 결과

1. `action=prepare`는 `_get_gstreamer()`의 import와 `Gst.init(None)`만 수행하며
   `Gst.parse_launch()`와 `nvv4l2h264enc`를 실행하지 않는다. Jetson probe의
   `nvenc_device_fds: []`, `gstreamer_mapped: true`와 일치한다.
2. `action`이 없는 기존 요청은 기본값 `encode`로 처리된다. persistent worker
   lock, timeout loop, process group 종료 로직은 기존 승인본과 같다.
3. `prepare_clip_encoder()`는 `record_state=False`를 사용하므로 H264 운영 상태
   통계를 변경하지 않는다. response 파일은 원자적으로 생성되고 finally에서
   정리된다. 격리 결과도 상태 불변과 잔여 파일 0개를 확인했다.
4. prepare가 실패하면 worker가 종료되지만, 다음 encode에서
   `_get_persistent_worker()`가 종료 상태를 확인하고 새 worker를 기동하므로
   재시도 가능하다. prepare 실패 자체는 main 추론 루프 진입을 막지 않는다.
5. 격리 증거는 “prepare가 NVENC/NVMM을 열지 않는다”는 주장에는 충분하다.
   GStreamer import 자체의 상주 메모리가 카메라+VadCLIP 환경에 미치는 영향은
   실카메라 시험 범위다.

## 실카메라 비교 시험 조건

- W 5회와 C 5회의 교차 순서, 매 회 tegrastats, 종료·메모리 회복 확인,
  조건별 2/5 실패 시 중단은 안전 지향적으로 합리적이다.
- 5+5 표본은 통계적 결론을 내리기에는 약하다. 결과는 운영 채택 확정이 아니라
  다음 진행 여부를 가르는 1차 신호로만 사용한다.
- 구분되지 않으면 VadCLIP 첫 실제 추론 전후 메모리 변화 조사로 넘어간다.
- 권장 사항: 이번 10회에 첫 추론 직전·직후 tegrastats 자동 샘플링을 포함해
  W/C 비교와 VadCLIP trigger 가설을 동시에 확인한다.

## 유지 조건

1. 카메라 반복 재시작 10회와 SIGTERM 무응답 재발 가능성을 사용자에게 알리고
   승인받은 뒤 시험한다.
2. 운영 main.py에는 시험 결과를 다시 보고하고 승인받기 전까지 반영하지 않는다.
3. Jetson main은 중지 상태를 유지하고 기존 커밋 `0fcbd0d`, `5728ae1`을 보존한다.
4. 후보 C의 운영 checkout 반영, push, revert는 이번 검수 승인 범위 밖이다.
