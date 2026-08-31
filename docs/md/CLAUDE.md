# 프로젝트 작업 규칙 (CLAUDE.md)

이 파일은 Claude Code가 세션 시작 시 자동으로 읽습니다.
캡스톤 드론 프로젝트(실시간 이상감지 순찰 드론) 관련 작업 시 아래 규칙을 따릅니다.

---

## 0. 프로젝트 기본 정보

- 팀: 3조 (고귀한, 서승현, 박성현, 서윤선), 지도교수 정은성
- 구성: FastAPI AI서버(DAE-vlm-main) + Spring Boot 백엔드(DAE_Backend-main) + React 프론트엔드(DAE_Frontend)
- 서버: `203.249.90.3` (SSH 별칭 `HPC-server`, 계정 `yunseon`, host `hydro1`), 프로젝트 루트 `/home/yunseon/Capstone/`
- 드론: Jetson(계정 `hpc@ubuntu`), 코드 경로 `~/drone_2026/code/`
- 1차 이상탐지 모델(Jetson): VadCLIP(CLIP ViT-B/16 기반), 2026-08-31 Jigsaw-VAD/WideBranchNet에서 교체 완료 (branch `vadclip-v4-20260831`)
- 통신: STOMP over WebSocket (`/ws`, SockJS 아님), 드론별 채널 `/topic/drones/{droneId}/commands`
- 관제 접속: `http://203.249.90.3:8031` (nginx 리버스프록시, 8080/8000 직접 접속 불가)

---

## 1. 파일 수정 원칙

1. **수정 전 반드시 최신 상태를 `view`/`cat`으로 먼저 확인**한다. 이전에 view한 내용은 신뢰하지 않는다(수정 이력이 쌓이면 라인 번호가 밀림).
2. 파일 일부만 바꿀 때는 `str_replace`류 도구를 쓰되, **교체할 텍스트 블록이 정확히 일치하는지** 반드시 재확인한다. 매칭 실패 시 대충 다시 시도하지 말고, 실제 파일 내용을 다시 조회해 정확한 텍스트로 재시도한다.
3. **수정 전 원본을 백업**한다 (`cp 파일 파일.bak_YYYYMMDD설명`).
4. 수정 후에는 **문법 검사**(`python3 -c "import ast; ast.parse(...)"` 등)로 문제없는지 확인한다.
5. 수정이 끝나면 **전체 파일을 다시 확인**(`cat`)해서 의도한 대로 반영됐는지 검증한다.

## 2. 코드/문서 백업 규칙

**2026-08-27부터: 코드+문서 모두 Google Drive 대신 git(단일 저장소 `Capstone_drone`)으로 전환.**
(Drive는 과거 이력 조회용으로만 남기고 더는 갱신하지 않음)

### 2-1. 저장소 구조: `https://github.com/miru0522/Capstone_drone` (private)

```
docs/
  md/     - CLAUDE.md 등 작업 규칙 문서
  docs/   - 참고용 문서 (Drive 요약 등)
jetson/
  code/   - Jetson 코드 스냅샷(정리된 뷰) - main 브랜치
  models/ - 양자화(TensorRT 컴파일) 전 원본 ONNX 모델
server/
  DAE-vlm-main / DAE_Backend-main / DAE_Frontend 소스코드만
  (weights/videodata/wavdata/profiledata/secret.yaml 등은 .gitignore로 제외 -
   서버의 /home/yunseon/Capstone/.gitignore 기준을 그대로 이식)
```

- **`main` 브랜치**: 위 구조로 정리된 스냅샷. docs/server는 여기서 직접 관리.
- **`jetson-live` 브랜치**: Jetson 실기의 `~/drone_2026/code/`가 **구조 변경 없이 그대로** 직접 push하는 브랜치(flat 구조, 전체 커밋 히스토리 보존). ⚠️ Jetson 실제 폴더명·경로는 "2026 연구자료" 성격상 앞으로도 `drone_2026`을 유지하기로 함 — git 저장소 안의 "jetson/" 이름은 어디 소속인지 구분하기 위한 것일 뿐, 실기 경로를 바꾸는 게 아님.
- Jetson → GitHub 인증: 저장소 전용 배포키(`~/.ssh/id_ed25519_github_drone2026`, write 권한, repo 단위로 범위 한정, Jetson `~/.ssh/config`의 `Host github.com`이 사용). 계정 전체 권한 PAT 아님.
- `.gitignore`(Jetson 쪽): `__pycache__/`, `logs/`, `test_videos/`, `*.engine`(TensorRT 엔진 — 하드웨어/버전 종속이라 백업 대상 아님, 필요시 재빌드) 제외.

### 2-2. 일상적인 커밋 워크플로

1. **Jetson 코드**: 지금까지처럼 `~/drone_2026/code/`에서 직접 `git add` → `git commit` → `git push`(자동으로 `jetson-live` 브랜치로 감). 구 규칙의 `파일.bak_YYYYMMDD설명` 수동 백업은 git 히스토리가 대신하지만, 실기 작업 중 즉시 롤백용 로컬 백업은 규칙 1-3대로 계속 병행.
2. **`main` 브랜치(docs/jetson 스냅샷/server)**: 이 PC(E:\univ)에서 관리. `jetson/code/`는 필요시 Jetson 최신 내용으로 수동 갱신(주기적 스냅샷 개념 - 실시간 동기 아님, 실제 이력의 원본은 `jetson-live` 브랜치).
3. **서버 코드(server/)**: 소스코드만 반영, weights/videodata/wavdata/secret 등 대용량·민감정보는 절대 커밋하지 않는다 (서버의 `.gitignore` 기준 준수).
4. 문서(세션정리 등)는 `docs/md/` 또는 `docs/docs/`에 마크다운으로 저장 후 커밋 (Drive 업로드 안 함).

### 2-3. VadCLIP 전환 이후 브랜치 현황 (2026-08-31 갱신)

- Jetson은 `vadclip-v4-20260831` 브랜치에서 작업 중이다(HEAD `7123cfa`).
- 2026-08-31: `origin/jetson-live`가 VadCLIP 이전(`c387b52`)에 정체돼 있던 것을 확인하고,
  `vadclip-v4-20260831`을 `jetson-live`로 fast-forward push해 최신화했다
  (`c387b52..7123cfa`). `Capstone_drone` repo `main` 브랜치의 `jetson/code/` 스냅샷도
  같은 시점 git archive 기준으로 갱신·커밋·push 완료(`a10ca5e`, `e952c7b`).
  이제 jetson-live/main 스냅샷/Jetson 로컬 상태가 모두 동일한 커밋(`7123cfa`)을 반영한다.
- 앞으로 Jetson에서 `vadclip-v4-20260831`에 새 커밋을 쌓을 경우, 그 브랜치에서
  `jetson-live`로 다시 fast-forward push해야 한다(자동 아님, 수동 확인 필요).
  Jetson git 상태 확인 시 `jetson-live`뿐 아니라 현재 활성 브랜치도 함께 본다.
- Rollback 기준점: `c387b52`(VadCLIP 이전 baseline) / branch `backup/pre-vadclip-20260828`.

## 3. 실기/서버 작업 원칙

1. **안전이 최우선**이다. 특히 킬스위치/착륙/배터리 관련 로직은 절대 임의로 되돌리거나 단순화하지 않는다.
2. 명령어는 **한 번에 하나씩** 실행하고 결과를 확인한 뒤 다음 단계로 진행한다. 여러 단계를 한 번에 묶어서 실행시키지 않는다(특히 실기 관련 작업).
3. **문제 진단 시 드론 코드와 서버 코드 양쪽을 모두 확인**한다. 드론 로그만 보고 결론 내리지 않는다 — 서버(Spring Boot) 컨트롤러/서비스 코드와 `docker logs`도 함께 대조한다.
4. 로그 파일은 `start_all.sh`/`stop_all.sh` 재시작 시 덮어써져 사라진다는 점을 항상 유의한다. 중요한 진단이 필요하면 재시작 전에 로그를 먼저 백업해두라고 안내한다.
5. 원인 불명 문제가 재발할 가능성이 있으면, **다음에 확인 가능하도록 진단 로그(상태값, 스택트레이스 등)를 미리 보강**해둔다.
6. **VadCLIP(main.py) 재시작은 `start_all.sh` 전체 재기동이 아니라 main.py 프로세스만** 종료 후 재시작한다 — 전체 재기동은 다른 팀원의 mavsdk_server/telemetry_sender/command_receiver까지 불필요하게 건드릴 수 있다.
7. `pkill python3` 금지 — VadCLIP main 외 다른 Python 프로세스까지 함께 종료될 수 있다.
8. `dae_*` 프로세스 종료 금지 — 팀원(서버측) 서비스 영역이다.
9. 카메라 이중 점유 금지 — main.py가 CSI 카메라를 사용 중일 때 별도 카메라 runtime을 동시에 실행하지 않는다(CaptureSession 충돌 원인).
10. Jetson 핵심 패키지(torch/CUDA/TensorRT/OpenCV) 조합을 임의로 재설치·업그레이드하지 않는다.

## 4. 문서 작성 원칙

1. 문서를 만들 때는 **용도를 먼저 확인**한다 — 사람에게 보여줄 것(배경 설명, 표, 설득 포함)인지, AI(서버측 등)에게 전달할 것(핵심 스펙만 간결하게)인지 구분해서 만든다. 애매하면 먼저 물어본다.
2. 세션 마무리 시, 그날 한 작업을 요약한 정리 문서를 만들어 Capstone_drone 저장소의 `docs/docs/`에 마크다운으로 저장하고 커밋·push한다(다음 세션이 이어받을 수 있도록 "다음에 할 일"을 명시). 2026-08-27부터 Drive 대신 이 방식 사용(2-2절 참고).
3. 로그 과다 출력(매초 반복되는 정상 상태 로그 등)은 실제 서버 전송 주기는 건드리지 않고, **로컬 로그 파일에 남기는 빈도만** 줄인다.

## 5. 대화 스타일

1. 한국어로 대화한다. 코드 주석/로그 메시지도 한국어를 그대로 사용해도 된다.
2. 불확실한 부분은 추측으로 넘기지 말고 **명확히 확인 질문**을 하거나, 실제 코드/로그를 조회해서 확인한다.
3. 안전/배터리/착륙처럼 중요한 변경사항은 이유와 함께 명확히 설명한다.

## 6. 세션 인계

- 새 세션(또는 새 Claude Code 세션) 시작 시, Capstone_drone 저장소 `docs/docs/`의 최신 세션정리 문서를 먼저 확인해 맥락을 파악한다(2026-08-27 이전 문서는 Drive 문서 폴더에 남아있음 - 과거 이력용).
- 이 프로젝트는 서버측 스펙이 계속 바뀌는 협업 구조이므로, 최근 서버팀 안내문/회신 문서가 있으면 우선 반영 상태를 재확인한다.

### 6-1. VadCLIP 재탑재 이후 미완료 작업 (2026-08-31 기준, 근거: `VadCLIP_모델_재탑재_및_Edge-Server_인수인계_20260831`)

- **P0**: 실제 Pixhawk `hover_now()` 안전 시험 — 현재까지 전부 MOCK hover로만 검증됨, 실비행/지상 안전 조건 및 관제·비행팀 합의 필요.
- **P0**: Threshold calibration — 현재 `ANOMALY_THRESHOLD=0.4073`은 UCF-Crime 기준 통합용 임시값, 드론 실데이터로 재보정 필요.
- P1: 실제 이상(폭력/절도/사고) recall 검증, 장시간 운영 시험(메모리/온도/오류), 서버 4-class 원시 로그 연동 확인.
- 위 P0 항목들은 안전/성능에 직결되므로 임의로 스킵하지 말고, 진행 전 사용자에게 먼저 확인한다.
