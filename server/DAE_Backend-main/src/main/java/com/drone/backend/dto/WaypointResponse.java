package com.drone.backend.dto;

import lombok.*;

@Getter
@Setter
@AllArgsConstructor

public class WaypointResponse {
    private Long step;
    private Double latitude;
    private Double longitude;
    private String address;
}
