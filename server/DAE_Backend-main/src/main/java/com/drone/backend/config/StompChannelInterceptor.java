package com.drone.backend.config;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
@Slf4j
public class StompChannelInterceptor implements ChannelInterceptor {

    @Value("${app.device-keys:}")
    private List<String> validKeys;

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor = MessageHeaderAccessor.getAccessor(message, StompHeaderAccessor.class);

        if (accessor != null && StompCommand.CONNECT.equals(accessor.getCommand())) {
            String deviceKey = accessor.getFirstNativeHeader("X-Device-Key");
            if (deviceKey != null) {
                if (!validKeys.contains(deviceKey)) {
                    log.warn("STOMP 연결 거부: 유효하지 않은 디바이스 키");
                    throw new IllegalArgumentException("Invalid Device Key");
                }
                log.info("디바이스 STOMP 연결 성공");
            }
            // 디바이스 키가 없으면 그냥 일반 유저 브라우저 연결로 간주 (권한은 Security에서 제어)
        }
        
        return message;
    }
}
