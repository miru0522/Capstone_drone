package com.drone.backend.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;
import java.util.Set;

@RequiredArgsConstructor
public class JwtFilter extends OncePerRequestFilter {

    private final JwtUtil jwtUtil;

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain) throws ServletException, IOException {
        // 0. /telemetry 요청은 JWT 검사 안 함 (패스) -> 로그인에 관계 없이 그냥 값을 받아야 하니까
        String path = request.getRequestURI();
        String method = request.getMethod();
        System.out.println("[JwtFilter] URI = " + path);  // 🔍 로그 찍어보면 바로 확인 가능

        // 인증 우회(permitAll)는 SecurityConfig에서 처리하므로, 여기서는 토큰 유무와 유효성만 검사합니다.



        String token = null;

        //  1. Authorization 헤더에서 먼저 찾기 (새로 추가!)
        String authHeader = request.getHeader("Authorization");
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            token = authHeader.substring(7); // "Bearer " 제거
            logger.info("token from Authorization header: " + token);
        }

        //  2. 헤더에 없으면 쿠키에서 찾기 (기존 코드)
        if (token == null) {
            Cookie[] cookies = request.getCookies();
            if (cookies != null) {
                for (Cookie cookie : cookies) {
                    if ("jwtToken".equals(cookie.getName())) {
                        token = cookie.getValue();
                        logger.info("token from cookie: " + token);
                        break;
                    }
                }
            }
        }

        // 토큰이 없거나 유효하지 않은 경우
        if (token == null) {
            logger.error("JWT 토큰이 헤더와 쿠키 모두에 없습니다.");
            filterChain.doFilter(request, response);
            return;
        }

        // 토큰 만료 및 유효성 검사 후 401 예외 처리
        try {
            io.jsonwebtoken.Claims claims = jwtUtil.getClaims(token);
            String name = claims.get("name", String.class);
            Long id = claims.get("id", Long.class);
            String role = claims.get("role", String.class);
            if (role == null) {
                role = "OPERATOR"; // 기존 토큰 호환성
            }

            // 인증 객체 설정
            UsernamePasswordAuthenticationToken authenticationToken =
                    new UsernamePasswordAuthenticationToken(name, null, List.of(new SimpleGrantedAuthority(role)));
            authenticationToken.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));
            SecurityContextHolder.getContext().setAuthentication(authenticationToken);

            filterChain.doFilter(request, response);
            
        } catch (io.jsonwebtoken.ExpiredJwtException e) {
            logger.error("Token이 만료되었습니다.");
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "토큰이 만료되었습니다.");
        } catch (Exception e) {
            logger.error("유효하지 않은 토큰입니다.");
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "유효하지 않은 토큰입니다.");
        }
    }
}