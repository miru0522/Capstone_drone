package com.drone.backend.config;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.Arrays;
import java.util.List;

@Configuration
@EnableWebSecurity
@RequiredArgsConstructor
public class SecurityConfig {

    @Value("${jwt.secret}")
    private String secretKey;

    @Value("${app.cors.allowed-origins}")
    private List<String> allowedOrigins;

    private final JwtUtil jwtUtil;
    private final DeviceKeyFilter deviceKeyFilter;

    @Bean
    public PasswordEncoder passwordEncoder(){
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity httpSecurity) throws Exception {
        httpSecurity
                .csrf((auth) -> auth.disable());

        httpSecurity
                .cors(cors -> cors.configurationSource(corsConfigurationSource()));

        httpSecurity
                .httpBasic((auth) -> auth.disable());

        httpSecurity
                .authorizeHttpRequests(auth -> auth
                        // 1. 로그인/가입 등 익명 허용 경로
                        // check-id는 회원가입 중(로그인 전)에 호출되므로 익명 허용이어야 한다.
                        // logout·verify-password는 본인 확인이 필요하므로 아래 authenticated로 남긴다.
                        .requestMatchers("/auth/login", "/auth/signup", "/auth/check-id",
                                         "/healthcheck", "/ws/**").permitAll()
                        // 2. 관리자 경로 (ADMIN 한정)
                        .requestMatchers("/admin/**").hasAuthority("ADMIN")
                        // 3. 디바이스 키 적용 대상 (Spring Security에서는 permitAll 하고 나중에 DeviceKeyFilter에서 차단)
                        // ⚠️ 메서드를 반드시 지정한다. "/events"만 쓰면 GET /events(이벤트 목록)까지 공개된다.
                        //    실제 차단은 DeviceKeyFilter가 X-Device-Key로 수행한다.
                        .requestMatchers(org.springframework.http.HttpMethod.POST, "/events").permitAll()
                        .requestMatchers(org.springframework.http.HttpMethod.POST, "/events/*/broadcast-complete").permitAll()
                        // 영상 프레임 업로드. 드론은 JWT가 없으므로 여기서 통과시키고
                        // DeviceKeyFilter가 X-Device-Key로 막는다.
                        // ⚠️ 아래 "/drones/**" authenticated 보다 반드시 위에 있어야 한다 (선매치).
                        .requestMatchers(org.springframework.http.HttpMethod.POST, "/drones/*/stream/frame").permitAll()
                        // 4. 특정 권한 요구 경로
                        // TTS 승인은 현장에 실제 경고 방송을 내보내는 조작이다.
                        // authenticated()로 두면 조회 전용(VIEWER)도 방송을 송출할 수 있다.
                        // 드론 명령이 canOperate로 VIEWER를 막는 것과 같은 기준을 적용한다.
                        // (이 프로젝트는 ROLE_ 접두사를 쓰지 않는다 — JwtFilter가 역할명을 그대로 권한으로 넣는다)
                        .requestMatchers("/events/*/tts-approval").hasAnyAuthority("ADMIN", "OPERATOR")
                        .requestMatchers("/events/**", "/wavdata/**", "/media/**", "/profile/**", "/drones/**", "/patrol-routes/**", "/users/**").authenticated()
                        // 5. 기타 모든 경로
                        .requestMatchers( "/**").authenticated()
                )
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
                )
                .addFilterBefore(deviceKeyFilter, UsernamePasswordAuthenticationFilter.class)
                .addFilterBefore(new JwtFilter(jwtUtil), UsernamePasswordAuthenticationFilter.class);

        return httpSecurity.build();
    }

    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();

        // 허용할 출처 (yml 파일에서 주입받은 리스트 사용)
        configuration.setAllowedOriginPatterns(allowedOrigins);

        // 허용할 HTTP 메서드
        configuration.setAllowedMethods(Arrays.asList("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"));

        // 허용할 헤더 (필요한 헤더 명시적으로 추가)
        configuration.setAllowedHeaders(Arrays.asList("Authorization", "Content-Type", "X-Requested-With"));

        // 인증 정보(쿠키)를 포함하도록 허용
        configuration.setAllowCredentials(true);

        // CORS 정책을 등록할 경로 설정
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);

        return source;
    }


}