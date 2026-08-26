package com.drone.backend.domain;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "user_drone_settings")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UserDroneSettings {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String userId; // 사용자를 식별하는 ID (예: admin)

    @Column(nullable = false)
    private String droneId;

    @Column(nullable = false)
    private boolean isVisible; // 사이드바 표출 여부

    @Column(nullable = false)
    private int sortOrder; // 정렬 순서
}
