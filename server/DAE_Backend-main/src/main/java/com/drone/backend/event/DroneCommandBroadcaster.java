package com.drone.backend.event;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Component;

import java.util.HashMap;
import java.util.Map;

/**
 * 드론 명령을 관제 화면들에 되돌려 알린다.
 *
 * {@code DroneCommandEvent}는 예전에도 발행되고 있었으나 <b>듣는 곳이 없었다.</b>
 * 그래서 관제사 둘이 같은 드론을 조작해도 서로의 명령이 보이지 않았다.
 *
 * 조작자가 없는 명령(경로·스테이션 저장)은 알리지 않는다 — 사람이 버튼을 눌러
 * 기체를 움직인 것만 서로 알아야 한다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class DroneCommandBroadcaster {

    private final SimpMessagingTemplate messagingTemplate;

    @EventListener
    public void onDroneCommand(DroneCommandEvent event) {
        if (event.getOperator() == null) return;

        Map<String, Object> payload = new HashMap<>();
        payload.put("droneId", event.getDroneId());
        payload.put("action", event.getCommand().get("action"));
        payload.put("operator", event.getOperator());
        payload.put("at", System.currentTimeMillis());

        messagingTemplate.convertAndSend("/topic/drones/commands", payload);
    }
}
