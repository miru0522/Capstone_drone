package com.drone.backend.dto;

import java.time.LocalDateTime;

/**
 * 비행 1회 요약. Flight History 목록에 쓰인다.
 * 궤적은 포함하지 않는다 — 목록이 무거워지면 안 되므로 상세 조회에서 따로 가져간다.
 */
public record FlightSessionResponse(
        LocalDateTime startedAt,
        LocalDateTime endedAt,
        int pointCount,
        double distanceM,
        Double maxAltM,
        Double batteryStart,
        Double batteryEnd,
        boolean inProgress   // 조회 구간 끝까지 착륙 기록이 없으면 true
) {}
