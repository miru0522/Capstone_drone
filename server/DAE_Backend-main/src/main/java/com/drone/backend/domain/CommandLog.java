package com.drone.backend.domain;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

/**
 * 관제사가 드론에 보낸 명령 한 건.
 *
 * 관제사가 둘 이상 붙으면 점유 개념이 없어 같은 드론에 서로 명령할 수 있다.
 * 실시간으로는 화면에 서로의 조작이 뜨지만(DroneCommandBroadcaster) 그것은
 * 지나가면 사라진다. <b>나중에 "그때 누가 착륙시켰나"를 찾으려면 남아야 한다.</b>
 *
 * <b>보낸 사실만 기록한다.</b> 드론이 실제로 받았는지는 확인하지 않는다 —
 * 규격에 COMMAND_ACK 가 있으나 우리가 구현하지 않았고, 전달 여부는 텔레메트리
 * 상태가 말해준다. 이 표의 목적은 "누가 무엇을 지시했나"다.
 */
@Entity
@Table(name = "command_logs", indexes = {
        // 조회는 거의 항상 "이 드론의 최근 조작"이다.
        @Index(name = "idx_command_logs_drone_time", columnList = "drone_id, timestamp")
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CommandLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "drone_id", nullable = false, length = 50)
    private String droneId;

    /** 통신 스펙의 action 값 (START_PATROL, LAND 등) */
    @Column(nullable = false, length = 40)
    private String action;

    /**
     * 그 시점의 관제사 이름을 문자열로 박는다.
     *
     * 계정을 참조하면 계정이 제거됐을 때 이력이 "알 수 없는 사용자"가 된다.
     * 누가 했는지가 이 표의 핵심이라 참조하지 않고 값으로 남긴다.
     */
    @Column(nullable = false, length = 50)
    private String operator;

    @Column(nullable = false)
    private LocalDateTime timestamp;
}
