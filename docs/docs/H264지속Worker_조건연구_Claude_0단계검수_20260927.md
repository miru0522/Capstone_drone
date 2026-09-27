# H264 지속 worker 조건 연구 Claude 0단계 검수

## 판정

**REVISE**

## MUST

1. 지속 worker도 매 요청 pipeline을 재생성하므로 warmup 가설을 정정
2. 3회 중 최선값 22.7%를 채택 신호가 아닌 참고치로 명시
3. 후보당 최소 20회, mp4v/H264 순서 무작위화
4. `nvpmodel`, `jetson_clocks` 상태 기록 및 실험 동안 유지
5. `maxperf-enable=true`는 비행 없는 유지보수 시간으로 제한

## SHOULD

- `writev` 구현 전에 raw 준비 구간 절대시간을 먼저 측정
- 지속 worker response 파일 fsync/IPC 시간을 별도 계측
- 측정 동안 `tegrastats`로 main.py 자원 경합 기록
- 종단 시험에서 업로드와 서버 분석시간 분리

## 승인된 1단계 범위

- 실제 운영 파일과 카메라를 변경하지 않는 `/tmp` 격리 시험
- 무작위 순서의 mp4v/H264 20회 이상
- 4Mbps/1.2Mbps 20회 이상
- raw 쓰기 방식은 구간 단독 프로파일링 후 효과가 있을 때만 구현

장시간 100회/30분, `maxperf-enable`, 실제 서버 업로드, 롤백 재시작은
비행 없는 유지보수 시간에만 수행한다.
