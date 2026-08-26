package com.drone.backend.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;

@Component
public class DeviceKeyFilter extends OncePerRequestFilter {

    @Value("${app.device-keys}")
    private List<String> validKeys;

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain) throws ServletException, IOException {
        String path = request.getRequestURI();
        String method = request.getMethod();

        boolean isDevicePath = path.equals("/events") ||
                path.matches("/events/\\d+/broadcast-complete") ||
                // 실시간 영상 프레임 업로드. 여기를 빠뜨리면 인증 없이 뚫린다.
                path.matches("/drones/[^/]+/stream/frame");

        if (isDevicePath && "POST".equalsIgnoreCase(method)) {
            String deviceKey = request.getHeader("X-Device-Key");
            if (deviceKey == null || !validKeys.contains(deviceKey)) {
                logger.warn("유효하지 않은 디바이스 키 요청: " + path);
                // ⚠️ sendError를 쓰면 안 된다.
                //    서블릿이 /error로 ERROR 디스패치를 걸고, /error는 SecurityConfig에서
                //    authenticated()에 걸린다. 익명 요청이므로 403이 되어 401을 덮어쓴다.
                //    드론은 401에 전송을 멈추도록 구현되어 있어 403은 정의되지 않은 값이다.
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.setContentType("text/plain;charset=UTF-8");
                response.getWriter().write("Invalid Device Key");
                return;
            }
        }

        filterChain.doFilter(request, response);
    }
}
