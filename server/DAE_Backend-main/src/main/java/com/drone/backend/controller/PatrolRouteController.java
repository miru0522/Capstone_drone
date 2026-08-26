package com.drone.backend.controller;

import com.drone.backend.config.JwtUtil;
import com.drone.backend.dto.PatrolRouteRequest;
import com.drone.backend.service.PatrolRouteService;

import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import java.util.HashMap;
import java.util.Map;



@RestController
@RequestMapping("/patrol-routes")
@RequiredArgsConstructor

public class PatrolRouteController {

    private final PatrolRouteService patrolRouteService;
    private final JwtUtil jwtUtil;

    // 순찰 경로는 팀 공용 자산이다. 조회는 전원, 생성·수정·삭제는 ADMIN만.
    private boolean isAdmin(String token) {
        return "ADMIN".equals(jwtUtil.getRole(token));
    }

    // 경로 등록 -> /patrolRoutes/patrolRoute-register
    @PostMapping
    public ResponseEntity<Map<String, Object>> registerPatrolRoute(
            @RequestBody PatrolRouteRequest.Register requestDto,
            HttpServletRequest request) {

        String token = jwtUtil.extractTokenFromRequest(request);
        Map<String, Object> response = new HashMap<>();

        if (token != null && jwtUtil.validateToken(token)) {
            if (!isAdmin(token)) {
                response.put("success", false);
                response.put("routeId", null);
                response.put("message", "경로 생성 권한이 없습니다. (관리자 전용)");
                return ResponseEntity.status(HttpStatus.FORBIDDEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(response);
            }

            Long routeId = patrolRouteService.registerPatrolRoute(requestDto);

            response.put("success", true);
            response.put("routeId", routeId);
            response.put("message", "경로가 성공적으로 등록되었습니다.");
            return ResponseEntity.ok(response);
        } else {
            response.put("success", false);
            response.put("routeId", null);
            response.put("message", "로그인이 필요합니다.");
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(response);
        }
    }

    // 경로 이름 중복 확인 -> /patrolRoutes/check-routeName
    @GetMapping("/check-name")
    public ResponseEntity<Boolean> checkRouteNameDuplicate(@RequestParam String routeName,
                                                         HttpServletRequest request) {
        String token = jwtUtil.extractTokenFromRequest(request);
        if (token == null || !jwtUtil.validateToken(token)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(false);
        }
        boolean exists = patrolRouteService.isRouteNameDuplicate(routeName);
        return ResponseEntity.ok(exists);
    }

    // 경로 조회 -> patrolRoutes/patrolRoute-search
    @GetMapping
    public ResponseEntity<?> getMyPatrolRoutes(HttpServletRequest httpRequest) {

        String token = jwtUtil.extractTokenFromRequest(httpRequest);
        if (token != null && jwtUtil.validateToken(token)) {
            return ResponseEntity.ok(patrolRouteService.getAllPatrolRoutes());
        } else {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("로그인이 필요합니다.");
        }
    }

    // 경로 이름·설명 수정 -> patrolRoutes/{routeId}
    // 지점(Waypoint)은 POST /waypoints/{routeId}로 따로 저장한다.
    @PatchMapping("/{routeId}")
    public ResponseEntity<?> updatePatrolRoute(
            @PathVariable Long routeId,
            @RequestBody PatrolRouteRequest.Update requestDto,
            HttpServletRequest httpRequest) {

        String token = jwtUtil.extractTokenFromRequest(httpRequest);
        if (token == null || !jwtUtil.validateToken(token)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("로그인이 필요합니다.");
        }

        if (!isAdmin(token)) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).body("경로 수정 권한이 없습니다. (관리자 전용)");
        }

        try {
            patrolRouteService.updatePatrolRoute(routeId, requestDto);
            return ResponseEntity.ok("경로가 수정되었습니다.");
        } catch (IllegalArgumentException e) {
            // 이름 중복·존재하지 않는 경로는 500이 아니라 400으로 구분해서 돌려준다
            return ResponseEntity.badRequest().body(e.getMessage());
        }
    }

    // (특정) 경로 삭제 -> patrolRoutes/{routeId}
    @DeleteMapping("/{routeId}")
    public ResponseEntity<?> deletePatrolRoute(
            @PathVariable Long routeId,
            HttpServletRequest httpRequest) {

        String token = jwtUtil.extractTokenFromRequest(httpRequest);
        if (token == null || !jwtUtil.validateToken(token)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("로그인이 필요합니다.");
        }

        if (!isAdmin(token)) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).body("경로 삭제 권한이 없습니다. (관리자 전용)");
        }

        boolean deleted = patrolRouteService.deletePatrolRoute(routeId);
        if (!deleted) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body("해당 경로를 찾을 수 없습니다.");
        }

        return ResponseEntity.ok("경로가 삭제되었습니다.");
    }
}
