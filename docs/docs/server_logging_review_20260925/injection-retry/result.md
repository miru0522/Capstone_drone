# 영상 주입 재시험 — 2026-09-25 22:01 KST

사용자의 재시도 요청으로 기존 안전 확인 조건에서 동일한 Assault006 영상을 7초간 주입했다. 코드·임계값·네트워크 설정·서비스를 변경하지 않았다.

- 22:01:22 주입 시작, 22:01:29 실제 카메라로 복귀.
- 22:01:28 VadCLIP score=0.985440으로 트리거.
- 호버 요청은 status=rejected, detail=unsafe_status:IDLE. 실제 호버 실행 성공 아님.
- 22:01:31 81프레임, 9fps, 5,510,253바이트 영상 인코딩 완료.
- nginx가 22:02:42에 POST /analyze-video에 HTTP 408 기록.
- Jetson은 22:04:23에 RemoteDisconnected('Remote end closed connection without response') 및 서버 응답 없음/실패 기록.
- 시험 중 AI 서버 로그는 출력 없음. VideoMAE/Qwen/백엔드 저장까지의 E2E 검증은 여전히 미완료.

## 새 진단 증거

Jetson의 서버 8031 대상 TCP 연결(로컬 포트 60730)을 두 차례 읽었을 때 bytes_acked=2,251,906, Send-Q=770,336에서 유지됐고, bytes_retrans는 7,770→9,218로 증가했다. 저장된 후속 상태는 tcp-state.txt에 있다. 전송 데이터 일부가 확인 응답되지 않고 재전송되는 정체를 관측했다. 이는 업로드 구간 문제라는 근거이며, Wi-Fi/AP/NAT/서버 네트워크 중 구체적으로 어디에서 손실되는지는 아직 확정할 수 없다.

## 다음에 할 일

업로드 연결의 양 끝 TCP 상태와 수신 바이트를 함께 관측해 정체 구간을 좁힌다. 이번 시험 결과만으로 분석 코드 수정이나 timeout 증가를 해결책으로 단정하지 않는다. 전송 문제 해결 후 같은 시험으로 신규 분석 로그 연결을 검증한다.

증거: jetson-events.txt, nginx-events.txt, hover-state.txt, tcp-state.txt.
