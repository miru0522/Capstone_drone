package com.drone.backend.domain;

public enum Role {
    ADMIN,      // 전체 관리 — 드론·경로 등록/수정/삭제, 계정 관리
    OPERATOR,   // 관제 — 순찰 명령 가능, 설정 변경 불가
    VIEWER      // 조회 전용 — 순찰 명령 불가
}
