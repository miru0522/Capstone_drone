package com.drone.backend.dto;

import lombok.*;

import java.time.LocalDateTime;

public class DroneResponse {
    @Getter
    @Setter
    @AllArgsConstructor
    public static class Search{
        private String droneId;      // 드론을 가리키는 유일한 값 (대리키는 노출하지 않는다)
        private String droneName;
        private String droneImage;
        // 수정 화면이 목록 데이터만으로 폼을 채울 수 있도록 점검일을 함께 준다.
        private LocalDateTime droneCheckdate;
        // 스테이션. 드론이 꺼져 있어도 지도에 홈 마커를 그리려면 목록 조회 시점에 필요하다.
        private Double stationLat;
        private Double stationLng;
    }


}
