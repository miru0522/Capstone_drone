# 분석 로깅 기능 배포 검증 (Claude, 2026-09-25 18:27 KST)

- 근거 승인: `claude-code-review-round1-approved.md` (COMPLETE_APPROVED, 승인 범위는 소스 반영+GitHub 백업, 컨테이너 재기동은 범위 밖으로 명시)
- 이번 문서의 역할: 위 승인 범위 밖으로 남겨졌던 **실제 컨테이너 재기동·15분 관찰**을 사용자 승인 하에 직접 수행하고 결과를 기록
- 수행자: Claude (통상 읽기 전용 검수, 이번 건은 사용자가 명시적으로 실행을 요청해 예외적으로 배포까지 수행)

## 1. 배포 전 상태 재확인

- HPC-server `~/Capstone/DAE-vlm-main`, `DAE_Backend-main`의 신규 파일 9개를 직접 SHA-256 재계산해 `manifest.json`과 전부 일치 확인(서버는 Linux라 줄바꿈 이슈 없이 바로 일치). 로컬 Windows 클론에서는 CRLF 체크아웃으로 1차 불일치가 났으나 LF 정규화 후 9/9 일치 확인 — 내용 자체는 승인된 버전과 동일함을 재확인.
- 배포 직전 `dae_ai_server`/`dae_backend` 모두 5~6일간 가동 중이던 구버전 컨테이너였고, 새 소스는 이미 서버 파일시스템에 반영돼 있으나 컨테이너 재기동 전이라 실제로는 구버전 코드가 돌고 있었음.
- 실제 젯슨(`DR-01`)은 배포 전후 모두 연결돼 있지 않음(가상 드론 `DR-SIM`만 연결) — 재기동이 실비행에 영향을 줄 위험 없음.

## 2. 배포 실행

```
cd ~/Capstone
docker compose -f docker-compose.yml -f compose.analysis-logging.yml up -d --build ai_server backend
```

- `ai_server`, `backend` 이미지 재빌드 성공(빌드 로그에 오류 없음, Java 쪽 `BUILD SUCCESSFUL`)
- 두 컨테이너 모두 `Recreate` → `Started`, 기동 후 37~38초 내 정상 응답 확인
- `dae_mariadb`, `dae_virtual_drone`, `dae_frontend` 등 무관 컨테이너는 손대지 않음

## 3. 15분 관찰 결과 (09:10:53 ~ 09:25:40 UTC, 재시작 직후부터)

| 확인 항목 | 결과 |
|---|---|
| `RestartCount` | `dae_ai_server`=0, `dae_backend`=0 (관찰 종료 시점까지 크래시 재시작 없음) |
| 컨테이너 상태 | 둘 다 `running` 유지 |
| 로그 회전 설정 적용 | `docker inspect`로 확인, 둘 다 `json-file, max-size=20m, max-file=5` 정상 반영 |
| 기본 응답 확인 | `ai_server /docs` → HTTP 200, `backend /events` → HTTP 400(파라미터 없는 GET이라 예상된 응답, 크래시 아님) |
| `error`/`exception`/`traceback`/`OOM`/`5xx` 패턴 검색 | 아래 4절 참고 — 전부 기존에도 있던 무해한 패턴으로 확인, **신규 결함 없음** |

## 4. 발견된 로그 패턴과 판정

### 4-1. `JwtFilter: JWT 토큰이 헤더와 쿠키 모두에 없습니다` (ERROR 레벨, 6회)
모든 발생 지점이 `[JwtFilter] URI = /ws` 직후였고, 직전 로그에 `WebSocketEventListener: 새로운 웹소켓 연결 감지`가 항상 함께 찍혔으며 이후 텔레메트리 수신이 끊김 없이 계속됨. 즉 STOMP `/ws` 핸드셰이크 단계(HTTP 업그레이드 요청)에는 JWT가 없는 게 정상이고 실제 인증은 STOMP CONNECT 프레임에서 이뤄지는 기존 동작 — **이번 배포로 새로 생긴 문제가 아니라 기존부터 있던 로그 레벨(ERROR로 찍히지만 기능은 정상)** 이슈로 판단. 연결 실패나 재시도 실패는 관찰되지 않음.
- 선택 개선(필수 아님): 이 로그를 ERROR가 아닌 DEBUG/INFO로 낮추면 향후 운영 로그 모니터링 시 오탐을 줄일 수 있음. 이번 배포와 무관하므로 이번 승인 범위에는 포함하지 않음.

### 4-2. `Transport error ... Unable to unwrap data, invalid status [CLOSED]` (DEBUG 레벨, 2회)
가상 드론의 주기적 재연결 시 이전 세션이 닫히는 과정에서 나는 정상적인 WebSocket 종료 로그. ERROR가 아니라 DEBUG 레벨이며 이후 즉시 새 세션이 재연결됨. 문제 아님.

### 4-3. 그 외
15분 동안 `error`/`exception`/`traceback`/`out of memory`/`refused`/`failed`/`5xx` 패턴으로 총 14줄이 잡혔고, 전부 위 두 패턴(4-1, 4-2)으로 설명됨. 그 외 신규 결함 신호 없음.

## 5. 이번 검증이 다루지 못한 것 (투명 공개)

- **관찰 창 안에서 실제 `/analyze-video` 요청이 발생하지 않았다.** 즉 이번에 추가된 `analysis_logging.py`/`AnalysisLog.java`의 신규 계측 코드 경로 자체는 이 15분 동안 실제로 실행되지 않았고, 컨테이너가 정상 기동하고 크래시하지 않는다는 것만 확인됐다. 신규 계측 코드가 실제 트래픽에서도 이전 코드 리뷰(§승인문서 3~4절, 26+5건 단위/통합 테스트)와 같은 방식으로 동작하는지는 **다음 실제 이상 트리거(또는 의도적 시험 업로드) 때 별도로 확인이 필요**하다.
- 가짜 사고 영상을 업로드해 강제로 트리거하는 것은 관제 서버에 불필요한 이벤트를 만들 수 있어 이번에도 수행하지 않았다(기존 Codex 보고서 §4와 동일한 이유).
- GPU 실추론 부하, 장시간(수 시간) 안정성, 로그 회전이 실제로 20MB를 채워 파일을 교체하는지는 15분으로는 확인 범위 밖이다.

## 6. 결론

**컨테이너 재기동은 성공했고, 15분 관찰 동안 이번 배포로 인한 신규 오류는 발견되지 않았다.** 발견된 로그는 전부 기존부터 있던 무해한 패턴(JWT 핸드셰이크 로그 레벨, 정상 재연결 종료)으로 확인됐다. 다만 신규 로깅 계측 코드 자체는 아직 실제 트래픽으로 검증되지 않았으므로, 다음 실제(혹은 승인된 테스트) 이상 트리거 발생 시 `analysis_logging`/`AnalysisLog` 출력이 계획대로 남는지 한 번 더 확인할 것을 권한다.

## 7. 증거

- 15분 모니터링 원본 로그: [`claude-deployment-monitor-20260925.log`](claude-deployment-monitor-20260925.log)
