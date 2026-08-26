package com.drone.backend.config;

import io.jsonwebtoken.*;
import io.jsonwebtoken.security.Keys;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Value;
import jakarta.annotation.PostConstruct;
import java.security.Key;
import java.util.Base64;
import java.util.Date;

@Component
public class JwtUtil {

    @Value("${jwt.secret}")
    private String secretKey;

    private Key key;

    @PostConstruct
    public void init() {
        this.key = Keys.hmacShaKeyFor(Base64.getDecoder().decode(secretKey));
    }

    @Value("${jwt.expiration:86400000}")
    private long expiration;

    public String generateToken(Long id, String name, String role) {
        return Jwts.builder()
                .setSubject("UserToken")
                .claim("id", id)
                .claim("name", name)
                .claim("role", role)
                .setIssuedAt(new Date())
                .setExpiration(new Date(System.currentTimeMillis() + expiration))
                .signWith(key)
                .compact();
    }
    public boolean isExpired(String token){
        return Jwts.parserBuilder().setSigningKey(key).build().parseClaimsJws(token)
                .getBody().getExpiration().before(new Date());
    }
    public Long getId(String token) {
        try {
            Claims claims = Jwts.parser()
                    .setSigningKey(key)
                    .parseClaimsJws(token.replace("Bearer ", ""))
                    .getBody();
            // claims에서 Id 추출
            return claims.get("id", Long.class);  // Long 타입으로 memberId 추출
        } catch (Exception e) {
            throw new IllegalArgumentException("유효하지 않은 토큰입니다.", e);
        }
    }
    public String getName(String token){
        String res = Jwts.parser().setSigningKey(key).parseClaimsJws(token)
                .getBody().get("name", String.class);
        System.out.println("res : " + res);
        return res;
    }

    /** 토큰의 역할(ADMIN/OPERATOR). role 클레임이 없는 구버전 토큰은 OPERATOR로 본다. */
    public String getRole(String token) {
        try {
            String role = Jwts.parser()
                    .setSigningKey(key)
                    .parseClaimsJws(token.replace("Bearer ", ""))
                    .getBody().get("role", String.class);
            return role != null ? role : "OPERATOR";
        } catch (Exception e) {
            throw new IllegalArgumentException("유효하지 않은 토큰입니다.", e);
        }
    }

    public Claims getClaims(String token) {
        return Jwts.parserBuilder().setSigningKey(key).build().parseClaimsJws(token).getBody();
    }

    public boolean validateToken(String token) {
        try {
            getClaims(token);
            return true;
        } catch (JwtException | IllegalArgumentException e) {
            return false;
        }
    }

    public String extractTokenFromRequest(HttpServletRequest request) {
        String auth = request.getHeader("Authorization");
        if (auth != null && auth.startsWith("Bearer ")) return auth.substring(7);
        Cookie[] cookies = request.getCookies();
        if (cookies != null) for (Cookie c : cookies) {
            if ("jwtToken".equals(c.getName())) return c.getValue();
        }
        return null;
    }


}