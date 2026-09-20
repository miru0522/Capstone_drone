# 항목 A `UPLOAD_MODE` 기동 로그 보강 결과 보고

- 작업일: 2026-09-20
- 승인 근거: `승인문서_항목A_UPLOADMODE로그_20260920_1141.md`
- 계획 근거: `보완계획서_Codex검수후속_20260920.md` 3절
- 대상: Jetson `~/drone_2026/code/`
- 실기 커밋: `f1fade2` (`fix: log analysis upload mode at startup`)

## 1. 적용 범위

승인된 항목 A만 적용했다. 배터리 단위 판정, RTL, 비행 명령 및 임계값은 변경하지 않았다.

변경 파일:

- `main.py`
- `131_upload_startup_logging_offline.py` 신규 추가

수정 전 백업:

- `main.py.bak_20260920_uploadmode_log_before`

## 2. 구현 내용

`main.py`가 `uploader.py`의 검증된 `UPLOAD_MODE`, `ANALYZE_URL`, `DRONE_ID`를 직접 참조하도록 했다. `if __name__ == "__main__":` 진입 직후 `log_upload_configuration()`을 호출하므로 카메라와 TensorRT 초기화 전에 실제 설정이 한 번 출력된다.

- B 모드: `INFO`
- A 모드: 영상 전용 구버전 호환 모드임을 `WARNING`
- A/B 이외 값: 기존 `uploader.py` 검증에서 import 단계에 `ValueError`
- 로그 제외 정보: `DEVICE_KEY` 등 비밀값

실기 시작 로그 원문:

```text
2026-09-20 11:51:25,065 [INFO] main: 분석 업로드 설정: mode=B, drone_id=DR-01, url=http://203.249.90.3:8031/analyze-video
```

이 로그는 `[Hover]` 준비, CSI 카메라 초기화, TensorRT 로드보다 먼저 출력됐다.

## 3. 시험 결과

| 시험 | 결과 | 근거 |
|---|---|---|
| `UPLOAD_MODE=B` 격리 테스트 | 통과 | INFO 1회, WARNING 없음 |
| `UPLOAD_MODE=A` 격리 테스트 | 통과 | 영상 전용 모드 WARNING 1회, INFO 없음 |
| `UPLOAD_MODE=invalid` 격리 테스트 | 통과 | `import uploader` 단계에서 `ValueError`, 카메라 미초기화 |
| `restart_component.sh main` 실기 확인 | 통과 | PID `33256`, 실제 환경 `UPLOAD_MODE=B`, 시작 로그 B |

추가 회귀 검사:

- `main.py`, `131_upload_startup_logging_offline.py` Python 문법 검사 통과
- `131_upload_startup_logging_offline.py`: 3/3 통과
- 기존 `130_upload_form_contract_offline.py`: 4/4 통과
- 두 번째 정상 기동 로그에서 `ERROR`, `CRITICAL`, `Traceback`, `InsufficientMemory`, `NvMapMem` 없음
- CSI 첫 프레임 확인 완료
- TensorRT CLIP visual 로드 완료
- VadCLIP warmup PASS
- 캡처 및 추론 약 9~10 FPS 복구

## 4. 배포 중 특이사항과 복구

첫 번째 재시작 PID `32012`는 설정 로그, 카메라 첫 프레임, TensorRT 로드와 warmup까지 완료했으나 이후 Argus `InsufficientMemory`/`NvMapMem` 오류가 한 차례 발생해 캡처 로그가 멈췄다.

`restart_component.sh main`의 SIGTERM 종료가 타임아웃되어 다음을 확인했다.

- `/proc/32012/cwd`: `/home/hpc/drone_2026/code`
- `/proc/32012/cmdline`: `python3 main.py`

대상 PID가 해당 작업 디렉터리의 `main.py`임을 검증한 뒤 PID `32012` 하나만 SIGKILL로 종료했다. `pkill python3`, 전체 파이프라인 재시작, `dae_*` 종료는 사용하지 않았다.

이후 `restart_component.sh main`으로 PID `33256`을 시작했다. 두 번째 기동에서는 Argus 메모리 오류가 재발하지 않았고 카메라, TensorRT, VadCLIP, 9~10 FPS 처리가 정상 복구됐다.

## 5. 커밋 및 동기화

- `origin/vadclip-v4-20260831`: `f1fade2`
- `origin/jetson-live`: `f1fade2`
- 커밋 본문에 승인 문서 `승인문서_항목A_UPLOADMODE로그_20260920_1141.md`를 근거로 기록했다.
- `main`의 `jetson/code/` 스냅샷에는 변경된 `main.py`와 신규 테스트를 반영한다.

## 6. 남은 확인

- 실제 이상 트리거에 의한 `/analyze-video` 요청과 관제 화면 점수 표시 E2E는 이번 진단 로그 변경 범위에서 다시 실행하지 않았다.
- 항목 B인 배터리 단위 판정과 RTL 일관성은 승인 범위 밖이므로 코드 변경하지 않았다.
