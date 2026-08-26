package com.drone.backend.controller;

import com.drone.backend.dto.ConnectionResponse;
import com.drone.backend.dto.Telemetry;
import com.drone.backend.service.TelemetryService;
import lombok.*;
import org.springframework.stereotype.Controller;
import org.springframework.messaging.handler.annotation.MessageMapping;

@Controller
@RequiredArgsConstructor
public class TelemetryController {

    private final TelemetryService telemetryService;
    private final org.springframework.messaging.simp.SimpMessagingTemplate messagingTemplate;

    /**
     * 드론(Jetson)으로부터 WebSocket(STOMP)을 통해 실시간 텔레메트리 수신
     * Destination: /app/telemetry
     */
    @MessageMapping("/telemetry")
    public void receiveTelemetryWebSocket(Telemetry telemetry) {
        if (telemetry.gps() != null) {
            System.out.println("[WS] ID: " + telemetry.droneId() + " | 위도: " + telemetry.gps().lat_deg() + " | 경도: " + telemetry.gps().lon_deg() + " | 고도: " + telemetry.gps().abs_alt_m());
        }

        // 1. DB 검증
        ConnectionResponse res = telemetryService.verifyAndRespond(telemetry);

        // 2. 등록된 드론일 때만 관제 대시보드(React) 구독 채널로 브로드캐스트.
        //    검증 결과를 버리면 미등록·퇴역 드론의 텔레메트리가 그대로 화면에 올라온다.
        if (res.connected()) {
            messagingTemplate.convertAndSend("/topic/telemetry", telemetry);
        }
    }
}