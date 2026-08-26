package com.drone.backend.config;

// WebSocketConfig.java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.*;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {
    private final StompChannelInterceptor stompChannelInterceptor;

    public WebSocketConfig(StompChannelInterceptor stompChannelInterceptor) {
        this.stompChannelInterceptor = stompChannelInterceptor;
    }

    @Override public void registerStompEndpoints(StompEndpointRegistry registry) {
        // 브라우저·드론 공용. SockJS를 걷어내 엔드포인트를 하나로 통일했다.
        // SockJS는 WebSocket이 막히던 시절의 호환 계층인데, 재접속은 @stomp/stompjs가
        // 담당하고 nginx에도 Upgrade 헤더가 있어 실익이 없었다. 게다가 /ws에 SockJS를
        // 켜면 그 아래가 통째로 SockJS 소유가 되어 드론용 문(/ws/raw)을 따로 내야 했다.
        registry.addEndpoint("/ws").setAllowedOriginPatterns("*");

        // TODO: 드론이 /ws로 전환을 마치면 제거한다. 전환 기간에만 남긴다.
        //       (백엔드를 먼저 올려도 옛 경로를 구독 중인 드론이 끊기지 않도록)
        registry.addEndpoint("/ws/raw").setAllowedOriginPatterns("*");
    }
    @Override public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic");
        registry.setApplicationDestinationPrefixes("/app");
    }

    @Override
    public void configureClientInboundChannel(org.springframework.messaging.simp.config.ChannelRegistration registration) {
        registration.interceptors(stompChannelInterceptor);
    }
}