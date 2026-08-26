package com.drone.backend.dto;

public record GPS(
        Double lat_deg,
        Double lon_deg,
        Double abs_alt_m,
        Double rel_alt_m,
        String status
) {}
