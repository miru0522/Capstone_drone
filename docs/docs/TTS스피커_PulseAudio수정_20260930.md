# Jetson TTS 스피커 PulseAudio 수정 (2026-09-30)

## 문제와 원인

- `PLAY_AUDIO` 처리 로그와 방송 완료 콜백은 성공하지만 USB 스피커에서 소리가 나지 않는 문제가 재현됐다.
- Jetson에서는 PulseAudio가 USB 스피커 sink를 관리하고 있었고, 기존 `aplay`는 raw ALSA 장치에 직접 접근해 PulseAudio와 충돌했다.
- 확인된 USB sink는 `alsa_output.usb-Jieli_Technology_UACDemoV1.0_4150354132313207-00.analog-stereo`이다.

## 반영 내용

- `jetson/code/command_receiver.py`의 TTS 재생을 `aplay`에서 `paplay`로 변경했다.
- `TTS_AUDIO_SINK`가 있으면 지정 sink를 사용하고, 없으면 `pactl list sinks short`에서 이름에 `usb`가 포함된 sink를 우선 선택한다.
- USB sink가 없으면 구버전 PulseAudio와 호환되는 `pactl info`의 `Default Sink:`를 사용한다.
- `paplay`/`pactl` 부재, PulseAudio 연결 실패, 재생 timeout, 비정상 종료 시 stderr를 포함한 오류를 기록한다.
- 오류 시 방송 완료 콜백을 보내지 않는다.
- raw ALSA 폴백은 무음 성공 오탐을 막기 위해 기본 비활성화했다. 필요한 경우에만 `TTS_ALLOW_APLAY_FALLBACK=true`로 켤 수 있다.
- 재생 timeout 기본값은 120초이며 `TTS_PLAYBACK_TIMEOUT_SEC`로 조정할 수 있다.

## 검증

- 로컬 및 Jetson `python3 -m py_compile`: 통과
- Jetson 동적 sink 탐색: USB sink 선택 확인
- Jetson 격리 시험: 1초 880Hz WAV를 `paplay`로 재생, 종료 코드 0
- 배포된 `play_tts_audio_base64()` 전체 경로 시험: base64 디코딩 → 임시 WAV → USB sink 재생 → 완료 로그 확인
- `command_receiver` 단독 재시작 후 STOMP `/topic/drones/DR-01/commands` 재구독 확인
- 재시작 당시 `mavsdk_server`가 실행 중이지 않아 기존 `start_all.sh`와 같은 설정으로 해당 프로세스만 복구했다. `main.py`와 카메라 프로세스는 건드리지 않았다.

## 한계와 다음 확인

- `paplay` 종료 코드 0은 PulseAudio가 오디오 스트림을 정상 수락했다는 뜻이다. 실제 스피커 진동·음압까지 소프트웨어만으로 확인할 수는 없다.
- 다음 실제 관제 `PLAY_AUDIO` 명령 때 사람이 음성을 듣고, 성공 로그와 방송 완료 콜백이 함께 남는지 최종 확인한다.
- Claude Code 검수를 시도했으나 방화벽/프록시 연결 거부로 실행되지 않았다. 대신 Jetson 격리 시험과 배포 후 전체 함수 시험을 수행했다.

## 이력

- Jetson 커밋: `2007b8f Use PulseAudio for TTS playback`
- `vadclip-v4-20260831`, `jetson-live` 브랜치에 push 완료
- Jetson 롤백 파일: `~/drone_2026/code/command_receiver.py.bak_20260930_tts_paplay_before`
