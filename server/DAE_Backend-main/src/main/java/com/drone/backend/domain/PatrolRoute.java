package com.drone.backend.domain;

import jakarta.persistence.*;
import lombok.*;

/**
 * 순찰 경로 — 이름이 붙은 웨이포인트 묶음.
 *
 * MAVLink의 {@code mission}이 아니라 {@code route}다. mission은 이륙·착륙·카메라 동작·
 * 파라미터까지 담는 프로토콜 개념인 반면, 우리가 저장하는 것은 순서 있는 좌표 목록뿐이다.
 * 실기 연동 시 드론 경계에서 MAVLink mission으로 변환한다.
 */
@Entity
@Table(name = "patrol_routes")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PatrolRoute {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "route_name", nullable = false, length = 16)
    private String routeName;

    @Column(name = "route_comment", length = 100)
    private String routeComment;

    @OneToMany(mappedBy = "patrolRoute", cascade = CascadeType.ALL, orphanRemoval = true)
    @Builder.Default
    private java.util.List<Waypoint> waypoints = new java.util.ArrayList<>();
}
