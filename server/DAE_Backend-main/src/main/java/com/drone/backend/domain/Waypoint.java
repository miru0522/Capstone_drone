package com.drone.backend.domain;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "waypoints")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Waypoint {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "patrol_route_id", nullable = false)
    private PatrolRoute patrolRoute;

    @Column(name = "step", nullable = false)
    private Long step;

    @Column(name = "latitude", nullable = false)
    private Double latitude;

    @Column(name = "longitude", nullable = false)
    private Double longitude;

    @Column(name = "address", length = 100)
    private String address;

    // 지면 해발고도. 외부 고도 API가 붙기 전까지는 null(=아직 모름)이다.
    @Column(name = "ground_altitude")
    private Double groundAltitude;

    @Column(name = "flight_altitude", nullable = false)
    private Double flightAltitude;

    // 목표 해발고도 = groundAltitude + AGL. 지면 고도를 모르면 함께 null이다.
    @Column(name = "target_altitude")
    private Double targetAltitude;

}
