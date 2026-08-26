package com.drone.backend.domain;

import jakarta.persistence.*;
import lombok.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "drones")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Drone {

    // 대리키. 행을 식별할 뿐이고 외부(API·페이로드·화면)에는 노출하지 않는다.
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // 업무키. 드론을 가리키는 유일한 값이며 기체 설정(MAVLink sysid 자리)과 일치해야 한다.
    // 변경 불가로 다룬다 — telemetry_history·event_logs·user_drone_settings가
    // 이 값을 FK가 아닌 문자열로 참조하므로, 바꾸면 과거 기록이 조용히 고아가 된다.
    @Column(name = "drone_id", nullable = false, length = 50)
    private String droneId;

    @Column(name = "drone_name", nullable = false, length = 15)
    private String droneName;

    @Column(name = "drone_image", length = 200)
    private String droneImage;

    @Column(name = "drone_checkdate")
    private LocalDateTime droneCheckdate;

    // 서버가 이 드론에게 "지시한" 경로. 드론이 지금도 들고 있다는 보장은 없다 —
    // 실제 보유 여부는 텔레메트리의 hasRoute가 진실이다.
    // 텔레메트리로는 좌표가 올라오지 않으므로 서버가 기억하지 않으면 아무도 모른다.
    //
    // 용도는 미리보기가 아니라 기록이다. 순찰이 시작되는 시점에 서버가 경로를 알아야
    // PatrolSession에 "지시 경로 스냅샷"을 남길 수 있다(telemetry_history_plan.md 2-3).
    //
    // @Lob 대신 TEXT를 쓴다. 지점 100개라도 4KB 정도라 TEXT(64KB)로 충분하고,
    // @Lob은 CLOB 스트림으로 다뤄져 드라이버 조합에 따라 성가시다.
    @Column(name = "last_route", columnDefinition = "TEXT")
    private String lastRoute;   // JSON: [{"lat":36.6,"lon":127.2,"alt_agl":50}, ...] — 드론에 보낸 정규화 형식

    // 스테이션(기지). 드론이 텔레메트리로도 보고하지만, 꺼져 있으면 알 수 없어
    // 지도에 홈 마커를 그릴 수 없다. 그래서 서버도 들고 있는다.
    @Column(name = "station_lat")
    private Double stationLat;

    @Column(name = "station_lng")
    private Double stationLng;
}
