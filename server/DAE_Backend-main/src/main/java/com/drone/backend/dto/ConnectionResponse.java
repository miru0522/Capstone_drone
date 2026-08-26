package com.drone.backend.dto;

public record ConnectionResponse(
        boolean connected,
        String droneId,
        String message,
        Double latitude,   // 위도
        Double longitude,  // 경도
        Double battery    // 배터리 퍼센트
) {}