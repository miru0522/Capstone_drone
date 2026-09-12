package com.drone.backend.event;

import java.util.Map;
import lombok.Getter;
import org.springframework.context.ApplicationEvent;

/**
 * 드론에 명령을 보냈다는 사실.
 *
 * 관제사가 둘 이상 접속하면 점유 개념이 없어 같은 드론에 서로 명령할 수 있다.
 * A가 「순찰 시작」을 누른 직후 B가 「안전 착륙」을 누르면 그대로 내려앉는데,
 * <b>A는 자기 명령이 취소된 것을 모른다.</b> 이 이벤트를 관제 화면으로 흘려
 * 누가 무엇을 지시했는지 서로 보이게 한다.
 *
 * 막지는 않는다. 잠금을 걸면 잠금이 남았을 때 아무도 드론을 못 만지게 되고,
 * 무조작 해제 시간·강제 해제 화면이 줄줄이 붙는다. 모르는 상태를 없애는 것이
 * 목적이다.
 */
@Getter
public class DroneCommandEvent extends ApplicationEvent {
    private final String droneId;
    private final Map<String, Object> command;
    /** 명령을 보낸 관제사 이름. 사람이 아닌 경로(경로·스테이션 저장)에서는 null */
    private final String operator;

    public DroneCommandEvent(Object source, String droneId, Map<String, Object> command, String operator) {
        super(source);
        this.droneId = droneId;
        this.command = command;
        this.operator = operator;
    }
}
