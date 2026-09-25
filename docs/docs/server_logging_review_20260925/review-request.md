# Claude 검수 요청 — 운영 기준 대비 로깅 변경만

## 판정 대상
E:/univ/Capstone_drone의 작업본. 기준 커밋 c58bea76d287c340b219b0295d89eb17fa9a17de는 실제 운영 AI 코드와 같고 GitHub backup/server-logging-baseline-20260924에 저장/원격 확인 완료했다. GitHub 옛 main에 없던 한국어 프롬프트/TTS는 기준본에 이미 포함되므로 이번 로깅 변경으로 간주하지 않는다.

사용자는 변경점만 검수받고 COMPLETE_APPROVED(완전승인) 이후에만 운영 소스에 적용하라고 요청했다. 코드는 아직 운영에 적용하지 않았다. READ-ONLY로 diff와 관련 파일/테스트를 검토하고 실질적인 결함은 반드시 지적한다. 수정·명령 실행·네트워크/운영 접속은 하지 않는다. 현재 브랜치 전체 리팩터링을 요구하지 말고 로깅 변경으로 인한 회귀/불완전 추적/정보 유출에 집중한다.

## 자료
- 같은 폴더 changes.diff: 기준 대비 로깅 소스, 테스트, 로그 회전 override의 diff.
- 같은 폴더 manifest.json: 호출자가 실제 파일 SHA256을 계산한 목록. 검수 후 다시 계산해 승인 대상의 변경 여부를 확인한다. 검수자의 shell 도구 부재는 소스 내용 승인과 분리한다.
- 같은 폴더 python-tests.txt 및 backend-tests.xml: 실제 테스트 결과.
- 실제 파일은 diff 경로에 따라 E:/univ/Capstone_drone에서 읽는다.
- 기존 계획: E:/univ/서버_분석_프로세스_로깅계획_v2_20260924.md. 아래 구현 구체화 사항을 반영해 검토한다.

## 변경 요약
1. AI JSONL 로거 및 최외곽 ASGI wrapper: 요청 UUID, body 수신/검증 오류, 단계 상태, HTTP 전송 결과, 요청별 terminal, monotonic 시간, 출력 오류 카운터. ContextVar로 요청 격리.
2. app.py: 수신/VideoMAE/Qwen/TTS/메타데이터 병합/변환/릴레이/정리 로그. X-Analysis-Id 추가. 모델 프롬프트/한국어 후처리/점수/파일 정책/응답 상태는 유지.
3. VideoMAE wrapper: observer 선택 인자와 내부 단계 관측만 추가. 기존 event_id 및 반환 스키마, 수치·판정 규칙 유지. 단독 CLI는 observer=None으로 종전 동작.
4. Java 필터/로거: 헤더 수신, 없는 ID 폴백, DB 이벤트 ID 연결, 최종 상태, 입력 원문을 제외한 스택 위치. EventController 파일 저장/매핑/DB/STOMP 단계 계측.
5. Python 26건, Java 5건의 격리 테스트. GPU·실제 DB·방송 없이 mocks로 실제 라우트/미들웨어·컨트롤러 실행. Python 4건은 실제 운영 원본과 HTTP 상태·JSON 응답 비교. VideoMAE 실제 predict AST를 추출해 계층 분류 계산 검증(실제 가중치 정확도 시험 아님).
6. 실제 Docker inspect에서 두 서비스가 json-file, 명시적 회전 옵션 없음으로 확인되어 선택 활성화용 compose.analysis-logging.yml 추가(서비스당 약 100MB 상한). 기존 docker-compose.yml을 수정하거나 서비스를 재시작하지 않는다.

## 구현 구체화·제한 (정직하게 판정에 반영)
- 이번 승인/적용 범위는 **소스 파일 반영과 GitHub 백업**이다. AGENTS.md에 dae_* 종료 금지가 있으므로 기존 컨테이너를 재시작/교체하지 않는다. 실제 활성화 및 GPU E2E는 팀원 배포 시 별도 수행한다.
- AI는 모델 이름/파일 크기·mtime/프롬프트 해시로 model_bundle_id를 만든다. 이는 가중치 내용 해시가 아니며 identity_kind에 명시된다.
- 운영 로그는 stdout JSONL, 예외 메시지/소스 줄/locals/프롬프트/영상/오디오/생성 전문/인증키를 기록하지 않는다. 프레임 위치만 남긴다. 백엔드 신규 분석 로그는 System.out으로 한 줄 JSON을 출력하며 기존 다른 서비스 SLF4J 설정은 바꾸지 않는다.
- stdout 동기 출력 방식이다. 출력 실패는 업무 예외로 전파하지 않고 누락 횟수를 다음 로그에 남긴다. OS 출력 자체가 장시간 블로킹되는 경우의 성능 보장은 없으며 비동기 큐는 도입하지 않았다.
- 초안의 14일/1GiB는 보관 제안이었다. 운영 로그 증가를 제한할 override는 20MB×5개다. 기간 보장을 주장하지 않는다. override 반영에는 나중에 서비스 재생성이 필요하다.
- Qwen 전체 wall time과 prepare/lock/generate/parse를 구분한다. GPU 순수 kernel 성능이나 촬영부터 판정까지 E2E 시간을 주장하지 않는다.
- 파일명 충돌/전송 timeout/부분 결과 제출/강제 재시도/관리자 승인 방송은 기존 동작을 유지한다. 이번 변경 이전 결함은 별도 참고로 분리한다.
- 계획서의 모든 운영 시험을 완료했다고 주장하지 않는다. 이 변경의 코드 반영 승인과 실제 활성화 검증은 다르다.

## 응답
1. COMPLETE_APPROVED / CHANGES_REQUIRED / CONDITIONAL 중 정확한 판정.
2. 필수 수정이 있으면 파일:라인, 재현 조건, 영향, 최소 수정안.
3. 테스트가 실제로 보호하는 것과 한계.
4. 선택 개선은 필수 조건과 구분.
결함이 없으면 명시적으로 COMPLETE_APPROVED라고 답하고 소스 반영 승인 범위를 명시한다. 승인 압박 없이 근거에 따라 판단한다. 검수 결과만 한국어로 출력한다.
