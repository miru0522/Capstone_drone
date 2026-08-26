package com.drone.backend.dto;

import lombok.*;

@Getter
@Setter
@AllArgsConstructor
// 요청 본문으로 들어오므로 Jackson이 쓸 기본 생성자가 필요하다.
// @AllArgsConstructor만 있으면 기본 생성자가 사라져 역직렬화가 실패할 수 있다.
@NoArgsConstructor
public class WaypointRequest {
    private Long step;
    private Double latitude;
    private Double longitude;
    private String address;


}