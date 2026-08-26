package com.drone.backend.domain;

import jakarta.persistence.*;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import java.time.LocalDateTime;

@Entity
@Getter
@NoArgsConstructor
@Table(name = "telemetry_history")
public class TelemetryHistory {
    
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "drone_id", nullable = false)
    private String droneId; // e.g. DR-01

    private Double latitude;
    private Double longitude;
    private Double altitude;
    private Double battery;

    // 드론이 보고한 상태. 비행 세션을 끊는 유일한 근거다.
    // PATROLLING | PAUSED | RETURNING | LANDING | IDLE
    // 이 컬럼 도입(2026-08-14) 이전 행은 null이라 세션 판정에서 제외된다.
    private String status;

    @Column(nullable = false)
    private LocalDateTime timestamp;

    @Builder
    public TelemetryHistory(String droneId, Double latitude, Double longitude, Double altitude, Double battery, String status, LocalDateTime timestamp) {
        this.droneId = droneId;
        this.latitude = latitude;
        this.longitude = longitude;
        this.altitude = altitude;
        this.battery = battery;
        this.status = status;
        this.timestamp = timestamp;
    }
}
