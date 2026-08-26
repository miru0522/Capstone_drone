package com.drone.backend.dto;

import lombok.*;

public class PatrolRouteRequest {
    @Getter
    @Setter
    @Data
    public static class Register{
        private String routeName;
        private String routeComment;
    }

    /** 경로 이름·설명 수정. 지점(Waypoint)은 /waypoints/{routeId}로 따로 저장한다. */
    @Getter
    @Setter
    @Data
    public static class Update{
        private String routeName;
        private String routeComment;
    }
}
