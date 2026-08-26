package com.drone.backend.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ExchangeStrategies;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientsConfig {

    @Bean("osrmClient")
    public WebClient osrmClient(@Value("${osrm.base-url}") String baseUrl) {
        return WebClient.builder()
                .baseUrl(baseUrl)
                .exchangeStrategies(ExchangeStrategies.builder()
                        .codecs(c -> c.defaultCodecs().maxInMemorySize(32 * 1024 * 1024))
                        .build())
                .build();
    }

    @Bean("jetsonClient")
    public WebClient jetsonClient(@Value("${app.ai-server.base-url}") String baseUrl) {
        return WebClient.builder()
                .baseUrl(baseUrl) // 예: http://192.168.0.44:8000
                .build();
    }

    @Bean
    public WebClient fastApiWebClient() {
        return WebClient.builder()
                .baseUrl("http://ai_server:8000")  // 쿠버네티스 서비스명
                .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}