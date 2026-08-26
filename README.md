# Capstone_drone

3조 캡스톤 - 실시간 이상감지 순찰 드론. 프로젝트 문서·Jetson 코드·서버 코드를 한 저장소로 통합.

## 브랜치 구성

이 저장소는 브랜치 2개로 구성된다.

### `main` — 정리된 스냅샷 뷰

```
Capstone_drone/ (main)
├── README.md                     - 이 파일
├── docs/
│   ├── md/CLAUDE.md               - 작업 규칙 문서 (파일 수정 원칙, 백업 정책, 실기/서버 작업 원칙 등)
│   └── docs/                      - 참고 문서
│       ├── DRIVE_SUMMARY.md
│       └── 세션정리_*.md          - 세션별 작업 정리 (다음 세션 인계용)
├── jetson/
│   ├── code/                      - Jetson 코드 "스냅샷" (main.py, command_receiver.py 등 + legacy/)
│   └── models/                    - 양자화(TensorRT 컴파일) 전 원본 ONNX 모델
│       ├── widebranchnet_n9.onnx
│       └── yolov5n.onnx
└── server/                        - 서버 소스코드만 (weights/videodata/wavdata/profiledata/secret 등 제외)
    ├── DAE-vlm-main/               - FastAPI AI 서버 (Qwen-VL 기반)
    ├── DAE_Backend-main/           - Spring Boot 백엔드 (src/main/java/com/drone/backend/...)
    └── DAE_Frontend/               - React 프론트엔드 (src/components, services, store)
```

### `jetson-live` — Jetson 실기 원본 (flat 구조, 실제 커밋 히스토리)

```
Capstone_drone/ (jetson-live)
├── main.py, command_receiver.py, telemetry_sender.py, ...   (jetson/ 접두어 없이 그대로)
└── legacy/
```

Jetson의 실제 폴더 구조 그대로 — 코드 변경 이력(버그 수정, 리팩터링 등)은 전부 이 브랜치에 커밋 단위로 쌓인다. `main`의 `jetson/code/`는 정리용 뷰일 뿐, 진짜 히스토리의 원본은 이 브랜치다.

## 물리적 위치 ↔ 브랜치 매핑

| 위치 | 실제 경로 | 관계 |
|---|---|---|
| **Jetson** (`hpc@ubuntu`, Tailscale) | `~/drone_2026/code/` | 폴더명·경로 변경 없음("2026 연구자료" 성격 유지). 여기서 `git push`하면 자동으로 **`jetson-live`** 브랜치로 감 |
| **HPC-server** (`yunseon@203.249.90.3`) | `/home/yunseon/Capstone/DAE-vlm-main` 등 | git 연결 안 됨(수동 반영). 소스코드만 `server/`로 스냅샷 복사 |
| **팀원 PC** | (자유) | `main` 브랜치 clone해서 `docs/`, `server/` 관리 |

**⚠️ main의 `jetson/code/`는 실시간 동기화가 아니다.** Jetson에서 코드를 고치면 `jetson-live`엔 바로 반영되지만, `main`의 `jetson/code/`는 필요할 때 수동으로 다시 복사해서 커밋해야 갱신된다. `server/`도 동일하게 스냅샷 방식(현재는 1회성, 지속 동기화 방식은 미정 - `docs/docs/` 세션정리 참고).

## 인증 (Jetson → GitHub)

- Jetson 전용 배포키: `~/.ssh/id_ed25519_github_drone2026` (이 저장소 한정 write 권한, 계정 전체 권한 PAT 아님)
- Jetson `~/.ssh/config`의 `Host github.com` 항목이 이 키를 사용하도록 설정됨

## 백업 정책 상세

`docs/md/CLAUDE.md` 2장 참고. 요약: 코드는 git(이 저장소), 문서는 `docs/docs/`에 마크다운으로 저장(Drive는 과거 이력 조회용으로만 유지).
