package com.drone.backend.dto;

import lombok.*;

public class PatrolRouteResponse {

    @Getter
    @Setter
    @AllArgsConstructor
    public static class Search {
        private Long routeId;      // ★ 추가
        private String routeName;
        private String routeComment;
    }
}
