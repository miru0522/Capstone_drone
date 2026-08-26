# Capstone_drone

3조 캡스톤 - 실시간 이상감지 순찰 드론. 프로젝트 문서·Jetson 코드·서버 코드를 한 저장소로 통합.

## 구조

```
docs/
  md/     - CLAUDE.md 등 작업 규칙 문서
  docs/   - 참고용 문서 (Drive 요약 등)
jetson/
  code/   - Jetson(hpc@ubuntu) 실제 실행 코드 (main.py, command_receiver.py 등)
  models/ - 양자화(TensorRT 컴파일) 전 원본 모델 (widebranchnet_n9.onnx, yolov5n.onnx)
server/
  DAE-vlm-main/     - FastAPI AI 서버 (Qwen-VL 기반)
  DAE_Backend-main/ - Spring Boot 백엔드
  DAE_Frontend/     - React 프론트엔드
  (weights/videodata/wavdata/profiledata/secret.yaml 등은 제외 - 서버의
   /home/yunseon/Capstone/.gitignore 기준을 그대로 이식)
```

## 실행 환경 (원본 위치, 변경 없음)

- Jetson 실제 런타임 코드는 여전히 `hpc@ubuntu:~/drone_2026/code/`에서 그대로 실행됨.
  이 저장소의 `jetson/code/`는 그 코드의 git 백업 사본. 런타임 디렉토리 자체를
  이 저장소 경로로 옮기는 건 아직 하지 않음(리스크 검토 필요, CLAUDE.md 참고).
- 서버 코드는 `yunseon@203.249.90.3:/home/yunseon/Capstone/`에서 그대로 운영됨.
  이 저장소의 `server/`는 소스코드 백업 사본(2026-08-27 기준 스냅샷).

## 백업 정책

`docs/md/CLAUDE.md` 참고.
