# 서버 분석 프로세스 로깅 계획 v2

- 용도: 서버팀과 AI 구현 담당자가 검토·구현할 기술 계획서.
- 기준: 2026-09-20 로컬 코드 스냅샷. 운영 서버의 최신 코드·worker 구성·수집 설정은 구현 착수 전 대조한다.
- 상태: 수정 계획 작성 완료, Claude 재검수 대상. 코드 적용·배포·실기 시험은 하지 않았다.

## 1. 목표와 범위

영상 한 건에 대해 수신, VideoMAE 판정 근거, Qwen 설명 생성, 자동 TTS, 결과 제출, 백엔드 저장, 관제 알림까지 로그로 재구성한다. 어느 단계가 성공·실패·생략됐는지와 소요시간을 구분한다.

필수 범위는 `/analyze-video` 요청과 그 요청이 호출하는 Spring Boot `/events`이다. 종료점은 서버 응답 전송과 서버 측 알림 발행까지이며, 실제 화면 표시와 드론 방송 완료는 동일한 의미가 아니다.

관리자 승인 후 TTS 재생성·방송은 별도의 후속 흐름으로 9절에 명시한다. 이 흐름과 프론트엔드 표시 확인은 확장 대상이며 이번 필수 구현의 완료 조건에 포함하지 않는다.

### 변경 범위

| 이번에 구현할 관측 변경 | 별도 기능 개선으로 분리 |
|---|---|
| 구조화 로그, 공통 ID 헤더, 단계 상태, 시간 계측, 진단용 내부 메타데이터 | 분류 규칙·임계값·모델·프롬프트 변경 |
| 기존 예외를 다시 전달하면서 실패 단계 기록 | TTS 실패 후 부분 결과를 계속 제출하는 정책 |
| 기존 파일 생성·삭제·보관 상태의 기록 | WAV 삭제, 파일명 생성 방식 변경, 보관 정책 변경 |
| 백엔드에서 분석 ID와 DB 이벤트 ID 연결 | 기존 평문 응답을 JSON으로 교체하거나 DB 컬럼 추가 |
| 잠금 대기시간과 현재 실행 환경 기록 | 새 추론 잠금, 큐, worker 수, 타임아웃·자동 재시도 추가 |

## 2. 실제 코드에서 확인한 처리 규칙

1. VideoMAE는 영상 디코딩/16프레임 추출/전처리 후 정상·이상 이진 분류와 이상 4종 분류를 계산한다. 정상에서도 4종 계산은 실행한다.
2. 최종 유형은 이진 argmax가 정상일 때 정상, 이상일 때 4종 argmax로 결정한다. 통합 5종 최고점 방식과 다르다.
3. 이상일 때만 Qwen 설명 생성과 자동 TTS를 실행한다. Qwen은 VideoMAE 유형을 입력받아 설명을 작성하며 독립적인 재판정기가 아니다.
4. Qwen 파싱 실패는 현재 예외 대신 대체 문자열을 반환한다. 이후 TTS/제출이 계속될 수 있으므로 처리 완료와 결과 품질을 구분해야 한다.
5. TTS 예외 등은 공통 예외 처리로 요청 실패를 일으킨다. 이미 수행한 VideoMAE/Qwen 결과가 자동으로 백엔드에 제출되지는 않는다.
6. eventData는 산출 데이터에 병합되며 유형·점수·드론 ID까지 덮어쓸 수 있다. 변경 전후 기록이 필요하다.
7. 백엔드는 파일 저장 → DB 저장 → STOMP 발행 순서다. 뒤 단계 실패가 앞 단계 성공을 되돌린다는 보장은 없다.
8. 백엔드 성공 응답은 이벤트 ID가 포함된 평문이고 AI 서버는 response.text를 그대로 반환한다.
9. AI finally는 원본/변환 MP4만 삭제한다. AI의 `tts_outputs`와 백엔드 `wavdata`는 다른 저장 영역이다. 백엔드 MediaRetentionScheduler 존재만으로 AI WAV 정리를 보장하지 않는다.

## 3. 공통 추적·로그 스키마

### ID 설계 — 기존 응답 계약 유지

- AI의 최외곽 ASGI 관측 미들웨어에서 `/analyze-video` 요청마다 UUID `analysis_id`를 새로 발급한다. 업로드 파일명·eventData·드론 입력 ID를 추적 ID로 사용하지 않는다.
- AI → 백엔드 `/events`에 `X-Analysis-Id` 헤더로 전달한다. 이는 새 관측용 헤더이며 기존 응답 본문·상태코드는 유지한다.
- 백엔드 필터가 유효한 UUID를 받아 요청 범위에 넣는다. 없거나 잘못됐으면 새 UUID를 만들고 `correlation_source=backend_generated`, 필요시 `invalid_correlation_header=true`를 기록한다. 잘못된 헤더만을 이유로 요청을 거절하지 않는다.
- 백엔드 DB 저장 성공 로그에 `analysis_id`와 `event_id`를 함께 남긴다. 이것이 두 ID의 연결 기준이다. AI 로그의 `event_id`는 이번 버전에서 null이어도 정상이며 평문을 억지로 파싱하지 않는다.
- 헤더 미반영/유실 시 서버 간 추적이 단절됨을 명시한다. 파일명으로 추정 연결하지 않는다. AI와 백엔드 동시 반영 및 격리 통신 시험 통과가 필수다.
- 요청마다 새 ID이므로 재업로드 중복을 제거하거나 같은 영상임을 증명하지 않는다. 전송 시도는 현재 단일 호출이므로 `attempt=1`; 재시도 기능은 추가하지 않는다.
- Python은 request context를 helper까지 전달하거나 ContextVar를 사용하고 요청 종료 시 reset한다. Java는 필터의 MDC를 finally에서 clear한다. 하위 모듈에 모호한 DB event_id 대신 analysis_id를 전달한다. 전역 mutable 변수로 요청 ID를 보관하지 않는다.

### 공통 필드

| 필드 | 정의 |
|---|---|
| `schema_version`, `timestamp`, `level`, `service` | 로그 스키마 버전, UTC ISO 8601 시각, 수준, 서비스명 |
| `instance_id`, `process_id`, `model_bundle_id` | 서버 재시작/프로세스 및 모델 묶음 구분. 기동 로그와 연결 |
| `analysis_id`, `event_id` | 요청 ID와 DB ID. 아직 없거나 해당 서비스가 모르면 null |
| `stage`, `event` | 고정 단계명과 started/completed/skipped/failed |
| `duration_ms`, `reason_code` | 단조 시계로 잰 단계 시간, 고정된 사유 코드 |
| `input_drone_id`, `submitted_drone_id`, `stored_drone_id` | 원래 요청, 병합 후 제출, 실제 DB 연결 드론 구분. 해당 단계에서만 기록 |
| `error_type`, `error_code`, `failed_stage` | 예외 분류와 실패 위치. 성공 시 생략 |

최종 요약의 단계 상태는 `not_attempted / started / completed / skipped / failed / unknown`을 사용한다. `unknown`은 통신 단절·프로세스 중단 등으로 결과를 확정할 수 없다는 뜻이다. Qwen 대체 문구나 원본 영상 대체는 별도 `quality=degraded`와 `fallback_used=true`로 표현한다.

## 4. 전체 처리 순서와 로그 선택

필수는 INFO 상시 기록, 상세는 DEBUG 선택 기록이다. 오류는 ERROR, 기능이 계속되는 대체·파싱·정리 문제는 WARN이다. 행마다 무조건 두 줄을 만들지 않고 표에 지정한 이벤트만 기록한다.

| 순서/단계 | 기록 선택·시점 | 핵심 값 |
|---|---|---|
| 1 `request` | 필수: ASGI 진입 started | analysis_id, 경로, 수신 시작 시각 |
| 2 `request_body` | 필수: 마지막 http.request body 수신 completed 또는 실패 | multipart 전체 수신 bytes, body_receive_ms. 파일 크기와 구분 |
| 3 `input` | 필수: 프레임워크 파싱·검증 이후 completed, 4xx는 미들웨어에 실패 기록 | 입력 드론, VadCLIP 값/존재, 영상 식별자. 라우트 진입 전 거절도 포착 |
| 4 `temp_store` | 필수: started/completed/failed | 실제 저장 영상 bytes, 파일 식별자, 시간 |
| 5 `videomae` | 필수: predict 호출 직전 started | 모델 묶음, 판정 규칙 버전 |
| 6 `video_decode_preprocess` | 필수: 완료 요약/실패; 추출 인덱스는 상세 | 원본 프레임 수, 실제 sampled_frames, 입력 shape, 디코딩/전처리 시간 |
| 7 `videomae_binary` | 필수: 완료/실패 | p_normal, p_anomaly, binary_label |
| 8 `videomae_subclass` | 필수: 완료/실패 | 계산 수행 여부. 4종 조건부 확률은 이상일 때 필수, 정상은 상세 선택 |
| 9 `videomae` | 필수: completed/failed | 유형/ID, is_anomaly, confidence, scores_5class, 전체 wall time |
| 10 `qwen` | 이상: 필수 started, 정상: skipped | category_input, prompt_version, skip_reason |
| 11 `qwen_prepare` | 필수: 완료 요약/실패 | 전처리 시간, 입력 프레임 설정. 내용 원문 제외 |
| 12 `qwen_lock` | 필수: 대기 started 및 획득 completed/실패 | lock_wait_ms, 이후 pre_sync_ms |
| 13 `qwen_generate` | 필수: started/completed/failed | generate_ms, 모델 ID |
| 14 `qwen_parse` 및 `qwen` | 필수: 파싱/전체 완료 또는 실패 | 섹션별 parse_ok, fallback_used, 문자열 길이, postprocess_ms, qwen_total_ms |
| 15 `tts_auto` | 이상: 필수 started/completed/failed, 정상: skipped | 음성 식별자, 생성 bytes, 시간. 설명 원문 제외 |
| 16 `metadata_merge` | 필수: 완료 요약, 파싱 문제 WARN | override_applied, 변경된 허용 필드 목록, 유형/점수/드론의 전후 값, 선택 점수 키 |
| 17 `submission_payload` | 필수: 구성 완료 | 병합 후 실제 제출 유형/점수/심각도, 텍스트 길이·파일 포함 여부 |
| 18 `video_convert` | 필수: started/completed/failed+fallback | 입력/출력 코덱(알 수 없으면 null), 변환 시간, 원본 대체 여부 |
| 19 `backend_submit` | 필수: started | analysis_id, 고정 대상 경로, 실제 첨부 bytes, attempt=1 |
| 20 `backend_receive` | 필수: 백엔드 필터/컨트롤러 수신·파싱 결과 | analysis_id, 메타데이터 파싱 상태, video/audio 존재 |
| 21 `backend_media_store` | 필수: 영상/음성별 started/completed/failed, 음성 없음 skipped | 파일 식별자·크기, 남은 저장 산출물 |
| 22 `db_save` | 필수: started/completed/failed | analysis_id+event_id 연결, 실제 저장 드론/유형/점수, source_key |
| 23 `alert_publish` | 필수: started/completed/failed | event_id, `/topic/events`, 제출 API 결과 |
| 24 `backend_submit` | 필수: AI에서 completed/failed | backend_http_status, 왕복시간. 응답 미수신이면 null 및 backend_outcome=unknown |
| 25 `cleanup` | 성공 상세, 실패 WARN; 요약은 최종 로그에 필수 | MP4 삭제/실패, WAV retained_by_current_behavior, 정리 미실행 파일 |
| 26 `request_terminal` | 필수: 미들웨어에서 요청별 단 한 번 | HTTP 응답/중단 상태, 단계 상태 요약, 마지막 단계, 전체 시간, 결과 품질 |
| 27 관제 화면 수신·표시 | 선택 확장 | 실제 수신/표시 확인 신호. 이번 구현은 표시 성공을 단정하지 않음 |

VideoMAE 부모 started는 전처리보다 먼저다. metadata_merge 후에 제출 스냅샷을 기록한다. 정상 분기의 Qwen/TTS는 이유 있는 skipped이고, 선행 오류로 미실행인 단계는 not_attempted다.

## 5. 점수·텍스트·메타데이터 기록 기준

- `vad_score`: Jetson anomaly_score. 누락은 null, 실제 0은 0.0. 백엔드에서는 `vadScore` 우선, `score` 폴백, 없으면 null이며 `source_key=vadScore/score/missing`을 기록한다. 외부 호출자가 있을 수 있어 score 폴백을 제거하지 않는다.
- `mae_p_normal`, `mae_p_anomaly`: 이진 softmax 결과. `mae_subclass_probs`는 이상 4종 조건부 확률이다.
- `mae_scores_5class`: 정상 확률 및 이상 확률×조건부 확률. `mae_confidence`는 선택한 유형의 확률이며 VadCLIP 이상 점수와 다른 값이다.
- 기존 wrapper의 반환 정밀도(소수 4자리)를 기준으로 기록한다. 미세 경계 분석용 raw logits/추가 정밀도는 기본 제외한다. 판정은 반올림 전 argmax로 이뤄져 표시 점수가 같아 보여도 결과가 다를 수 있다.
- 정상의 stage2=None은 미실행이라는 뜻이 아니다. `subclass_executed=true`, `subclass_probs_omitted_reason=normal_policy`를 기록한다. 정상 조건부 확률을 DEBUG로 남기려면 wrapper 내부에서 계산 직후 기록하며 기존 응답 스키마는 바꾸지 않아도 된다.
- 점수 범위/NaN/타입 이상은 관측용 quality flag로 표시하고 JSON에는 유한 수치 또는 null만 기록한다. 진단 때문에 기존 판정·입력 수용 정책을 바꾸지 않는다.
- 병합 전 모델 결과, 병합 후 제출 결과, DB 저장 결과를 서로 구분한다. eventData 전체나 알 수 없는 키·값을 그대로 로그에 쓰지 않는다. allowlist 필드의 변경 플래그와 안전하게 직렬화한 값만 남긴다.
- Qwen 파싱 성공 여부는 대체 문구와 문자열 비교로 추측하지 않고 `_grab_section`의 실제 추출 결과로 결정한다. 섹션별 boolean/길이 메타데이터를 내부적으로 보강하되 기존 반환 문구는 유지한다.
- Qwen 결과 전문의 현 저장 위치는 EventLog.vlmSituationDesc / vlmTtsCandidate다. 이는 병합 후 제출된 내용이며 원래 Qwen 출력과 같다고 단정하지 않는다. 저장 전 또는 제출 실패 시 DB 전문 조회는 불가능하다. 이번에는 전문 보존을 새로 추가하지 않고 길이/파싱/변경 여부만 관측한다.

## 6. 시간 측정과 요청 종료의 의미

- 시각은 UTC, 서비스 내부 시간은 Python perf_counter / Java nanoTime으로 측정한다. 서로 다른 서버의 monotonic 값을 빼지 않는다.
- ASGI body 수신 래퍼는 메시지를 관찰하고 그대로 전달한다. 본문을 별도 재소비/복제/저장하지 않는다. HTTP multipart bytes와 영상 파일 bytes는 다르다.
- 서버가 보는 request/body 시간은 nginx 버퍼링·네트워크 토폴로지의 영향을 받는다. Jetson 업로드 전체 시간이나 카메라 촬영부터 판정까지의 시간으로 부르지 않는다. 첫 ASGI 진입 이전 대기시간은 측정 범위 밖이다.
- 라우트 실행 이전 FastAPI 검증 오류·body disconnect도 최외곽 미들웨어가 관측한다. 라우트 단계 상태는 not_attempted로 남는다. nginx/서버가 ASGI 이전에 거절한 요청은 프록시/서버 접근 로그 영역으로 분리한다.
- Qwen: prepare_ms, lock_wait_ms, pre_sync_ms, generate_ms(기존 후속 CUDA synchronize 포함), postprocess_ms, total_ms를 구분한다. lock_wait는 with 진입 직전부터 획득 직후까지, pre_sync는 기존 첫 synchronize를 따로 잰다. 새 CUDA 동기화를 추가하지 않는다.
- VideoMAE 외부 predict wall time을 필수로 측정한다. 기존 latency_ms는 time.time 기반이므로 별도 legacy 값으로 취급하거나 새 monotonic 진단값을 쓴다. 이 시간은 순수 GPU kernel 시간이라고 주장하지 않는다.
- 현재 async 라우트 안의 동기 추론/HTTP 호출과 worker/다른 엔드포인트가 동시성에 영향을 준다. 잠금 유무만으로 동시 실행을 단정하지 않는다. 배포 시 worker 수·프로세스 수·device 정보를 기동 로그로 남긴다.
- request_terminal은 최외곽 관측 래퍼 한 곳이 소유한다. ASGI 최종 body send 완료 여부와 앱 반환/예외·정리 결과를 추적하고 wrapped app 종료 시 finally에서 1회 기록한다. `response_sent=true`는 ASGI send 완료이며 Jetson의 실제 수신 확인은 아니다. handler return 직전은 최종 전송 완료가 아니다.
- 백엔드도 필터 한 곳에서 최종 요약을 남긴다. 서비스별 최종 로그가 각각 한 건인 것이 정상이다. 단계 오류 상세는 최초 실패 지점에 1회, 최종 요약에는 참조와 상태만 남긴다.
- 강제 종료/OOM kill에서는 finally 자체가 실행되지 않을 수 있다. 이 경우 completed/failed를 조작하지 않고 started 후 terminal 없음으로 분류한다. 별도 수집기에서 오래 미종료된 요청을 `suspected_stall/unknown`으로 찾는다. 경과시간만으로 실패 확정이나 자동 재시작을 하지 않는다.

## 7. 실패·부분 성공 표현과 관측의 한계

| 상황 | 기록할 상태 | 이번에 바꾸지 않는 동작 |
|---|---|---|
| Qwen 파싱 실패 후 대체 문구 반환 | qwen completed, parse_ok=false, quality=degraded; 이후 실제 진행 기록 | 대체 문구·TTS 호출 정책 |
| VideoMAE/Qwen 성공 후 TTS 예외 | videomae/qwen completed, tts failed, submit not_attempted | 부분 결과를 새로 제출하지 않음 |
| 영상 변환 실패 후 원본 사용 | convert failed, fallback_used=true; submit 별도 | 기존 원본 전송 |
| 백엔드 파일 저장 성공 후 DB 실패 | media completed, db failed/결과 불명 시 unknown, 남은 파일 참조 | 자동 삭제/롤백 추가 없음 |
| DB 성공 후 STOMP 실패 | db completed+event_id, publish failed, backend HTTP 500 가능 | 자동 재발행/중복 억제 추가 없음 |
| 백엔드 응답이 유실됨 | AI submit failed, backend_outcome=unknown | DB 미저장으로 단정하지 않음. 백엔드 로그로 확인 |
| 백엔드 non-200 | 원래 backend_http_status와 AI 실제 response_status 별도 | 현재 공통 except가 상태를 500으로 바꾸는 동작 수정은 별도 |
| MP4 정리 실패 | 주 처리 결과 유지, cleanup failed/WARN | 성공을 전체 실패로 바꾸지 않음 |
| 강제 종료 | 마지막 started와 terminal 없음 | 성공/실패 추정 생성 없음 |

예외 타입/메시지/스택은 최초 예외 지점에서 수집한다. VideoMAE wrapper가 예외를 error dict로 바꾸기 때문에 wrapper except에도 기록 지점이 필요하다. 상위에서는 같은 스택을 중복 출력하지 않는다. 정리 실패가 원래 실패 원인을 덮어쓰지 않게 한다.

## 8. 파일·로그 수명주기 및 운영

- 파일 역할을 `ai_temp_original`, `ai_temp_web`, `ai_tts_output`, `backend_video`, `backend_audio`로 구분한다. 생성/전송/기존 삭제 결과를 기록한다.
- AI WAV는 현 코드에서 요청 종료 시 삭제되지 않는다는 사실을 retained_by_current_behavior로 기록한다. 영구 보존이나 영구 누수라고 단정하지 않는다. 외부 정리 작업과 `/tts` FileResponse 이용을 확인한 뒤 삭제 정책은 별도 설계한다.
- 파일명을 바꾸지 않고 관측용 artifact_id를 발급한다. 로그 식별용 참조는 경로 대신 역할+artifact_id 또는 정규화 경로의 해시를 사용한다. 파일명 충돌을 해결했다고 주장하지 않는다.
- 운영 로그는 UTF-8 JSONL. 원본 영상/음성/base64/프롬프트/생성 텍스트/인증 헤더/쿠키/원문 응답 본문은 제외한다. 오류 메시지·스택의 예외 문자열에도 같은 redaction을 적용하며 locals는 수집하지 않는다. 길이 제한과 개행 이스케이프를 둔다.
- 출력 수집은 컨테이너 stdout 수집기를 우선 사용한다. 애플리케이션/컨테이너가 같은 파일을 중복 회전하지 않게 단일 책임을 정한다. 서비스별 초기안은 14일 또는 총 1GiB 중 먼저 도달한 한도이며, 실제 발생량·기존 운영 설정을 보고 배포 전 확정한다. 용량 한도에 걸리면 14일 보존이 보장되지 않음을 표시한다.
- 인증 실패 등 매 요청 원문을 출력하지 않는다. 정상 프레임별·토큰별 반복 로그는 제외하고 기존 동일 단계 print는 대체해 중복을 줄인다. 정상 영상은 Qwen/TTS 내부 이벤트를 만들지 않는다.
- 모델/가중치 식별값과 프롬프트 버전은 기동 시 1회 기록하고 요청은 model_bundle_id로 참조한다. 가중치 해시를 요청마다 계산하지 않는다.
- 로거 직렬화/출력 실패가 분석 예외를 유발하지 않게 한다. bounded 비동기 큐를 사용할 경우 overflow 정책을 명시하고 누락 카운터·주기적 요약을 수집한다. 누락이 있으면 추적 완전성 미충족으로 표시한다. 기록 유실 없이 무제한 메모리 사용한다는 보장은 하지 않는다.

## 9. 별도 후속 흐름: 관리자 승인·TTS 재생성·드론 방송

필수 분석 흐름 이후 독립적으로 발생한다. event_id를 기준으로 연결하며 `flow=approved_broadcast`와 별도 action_id를 사용한다.

| 단계 | 확장 시 남길 내용 |
|---|---|
| 관리자 승인 요청·중복 승인 분기 | event_id, action_id, 승인 상태 저장 결과, 중복 생략 |
| 비동기 작업 예약/시작 | 예약 성공과 실제 실행 시작 구분. HTTP 200은 방송 완료가 아님 |
| FastAPI `/tts` 재호출 | 새 요청 ID, parent action_id, 시간, 빈 오디오/오류 |
| WAV 저장·DB 음성 경로 갱신 | 각각의 성공/실패 및 파일 참조 |
| 대상 드론 확인 | 배정 없음이면 PLAY_AUDIO skipped, 음성 생성 성공은 유지 |
| PLAY_AUDIO 발행 | 명령 발행 결과. audioBase64 제외 |
| broadcast-complete 콜백 | 콜백 수신, 상태 DB 저장, 관제 상태 알림을 각각 기록 |

비동기 Java 작업에는 MDC가 자동 전파된다고 가정하지 않는다. 명시적으로 ID를 전달하고 실행 scope 종료 시 정리한다. 콜백 미수신을 방송 실패로 단정하지 않는다. 이번 필수 변경으로 관리자 승인/방송을 실행하지 않는다.

## 10. 구현 위치·순서와 검증 기준

### 구현 순서

1. 운영 코드/배포 방식 대조, 헤더 전달 경로 확인, 기존 로그 수집 및 보관 설정 확정.
2. ASGI 관측 미들웨어와 Spring 필터/MDC, 공통 JSON 스키마 및 redaction 구현. 기존 응답 본문과 상태 보존.
3. app.py의 주요 단계와 videomae_infer.py의 내부 전처리/분류/예외 지점 계측. Qwen 내부 파싱 메타데이터 계측.
4. EventController의 파일 저장/DB/STOMP 상태 및 ID 매핑 로그 추가.
5. 격리 시험으로 아래 수용 기준 검증. 로그 순서·필드·원래 응답 동작을 함께 비교.
6. 서버팀과 배포 범위를 맞춘 뒤 반영. 운영 실기 트리거·방송·재시작은 이 계획 작성 작업에서 수행하지 않는다.

### 필수 격리 검증

| 시나리오 | 수용 기준 |
|---|---|
| 정상 및 이상 4종 | 결과·점수·기존 응답이 계측 전과 동일, 정상 Qwen/TTS skipped, 요청 ID 연결 |
| vadScore 누락/0 및 score 폴백 | null/0 구분, 선택 키 기록 |
| 깨진 영상/디코딩 오류 | wrapper 최초 실패 스택 1회, 이후 미실행, 최종 요약 1회 |
| 잘못된 폼/누락 필드/본문 중단 | 라우트 미진입이어도 ASGI 도달 요청 ID와 종료 상태 존재 |
| Qwen 섹션 하나/둘 누락 | 각각 parse_ok=false, degraded, 실제 후속 동작 유지 |
| TTS 예외 | 이전 분석 완료 로그 보존, 제출 미실행, 실제 HTTP 오류와 일치 |
| 변환 실패 | 실패와 원본 대체가 함께 기록되고 실제 첨부와 일치 |
| eventData 덮어쓰기/파싱 실패 | 모델·제출·저장 값 구분, 원문 민감값 제외 |
| 파일 저장 성공→DB 실패 / DB 성공→STOMP 실패 | 앞 단계 성공 보존, 이벤트 ID 가능 시 연결, 후속 실패 구분 |
| 백엔드 4xx/5xx/응답 유실 | backend_status와 AI status 분리, 유실은 unknown |
| 헤더 없음/손상/정상 및 동시 요청 | 폴백 명시, 정상은 동일 ID 연결, 요청 간 context 혼입 없음 |
| MP4 삭제 실패/WAV 보관 | cleanup WARN과 주 결과 분리, 보관 상태를 삭제 성공으로 기록하지 않음 |
| 로거 직렬화/출력 실패 | 본래 판정·응답 유지, 누락을 관측 가능, 비밀값 노출 없음 |
| 강제 중단(격리 프로세스만) | terminal 없는 요청을 unknown으로 식별, 거짓 완료 로그 없음 |

각 서비스의 정상 종료 요청에는 request_terminal 1건. 판정 성공·제출 성공·DB 성공·알림 발행 성공·화면 표시 성공은 서로 다른 상태로 확인한다. 성능 비교는 같은 입력/환경의 계측 전후 wall time·로그 bytes·p50/p95로 측정하고, 운영에 영향을 주는 증가가 있으면 상세 이벤트 빈도를 조정한다. 현재 성능 수치는 미측정이며 성능 검증 완료를 주장하지 않는다.

## 11. 1차 검수 의견 처리

| 지적 | 반영 판단 |
|---|---|
| 승인 기반 방송 누락 | 후속 흐름 전체를 9절에 추가. 원래 판정 출력 범위 밖이므로 확장으로 구분 |
| event_id 연결 불가 | analysis_id 헤더 및 백엔드 DB 로그 매핑으로 해결. AI event_id 필수 요구 삭제 |
| TTS 실패로 전체 미제출 | 관측 상태로 명시. 부분 제출 기능 변경과 분리 |
| WAV 정리 누락 | 현 보관 상태와 확인 과제 명시. 무조건 삭제 제안은 미수용 |
| 잠금 대기 계측점 없음 | acquire 전후 및 pre-sync 경계 추가 |
| VideoMAE 잠금 부재 | 동시성/경합 측정 한계 명시. 잠금 추가는 미수용 |
| score 폴백/결과 저장소/DB 후 알림 실패 | 입력 출처, 실제 DB 컬럼, 단계별 부분 성공으로 반영 |

## 12. 코드 근거

모든 경로는 `E:/univ/code_review_source_260920/` 기준이다.

- `server/DAE-vlm-main/app.py`: `_parse_vlm_sections`, `_run_vlm_inference`, `_synthesize_tts`, `/tts`, `_to_browser_mp4`, `/analyze-video`.
- `external_runtime/server/videomae/videomae_infer.py`: 프레임 샘플링/전처리, predict의 계층 판정과 반환/예외 처리.
- `server/DAE_Backend-main/src/main/java/com/drone/backend/controller/EventController.java`: receiveVideoEvent, approveTts, broadcastCompleteCallback.
- `server/DAE_Backend-main/src/main/java/com/drone/backend/service/TtsService.java`: 비동기 재생성/저장/PLAY_AUDIO.
- `server/DAE_Backend-main/src/main/java/com/drone/backend/service/MediaRetentionScheduler.java`: 백엔드 미디어 정리. AI tts_outputs 정리 증거로 간주하지 않음.
- `server/DAE_Frontend/src/services/websocket.js`, `server/DAE_Frontend/src/components/history/IncidentDetail.jsx`: 관제 구독·표시, 서버 발행과 화면 표시의 경계.
