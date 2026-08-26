package com.drone.backend.dto;

public record Battery(
        Double remaining_percent,
        String status
) {}
