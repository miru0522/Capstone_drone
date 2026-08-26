package com.drone.backend.dto;

import java.util.List;

public class Mission {

    public record WaypointDto(
            int seq,        // step
            double lat,     // latitude
            double lon,     // longitude
            double alt      // flightAltitude or targetAltitude 중 선택
    ) {}

    public record MissionReq(
            List<WaypointDto> waypoints,
            boolean auto_takeoff
    ) {}

    public record MissionRes(
            String status,
            Integer count
    ) {}
}
