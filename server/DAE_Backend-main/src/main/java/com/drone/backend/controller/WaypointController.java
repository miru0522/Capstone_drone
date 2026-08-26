package com.drone.backend.controller;

import com.drone.backend.dto.WaypointRequest;
import com.drone.backend.dto.WaypointResponse;
import com.drone.backend.service.WaypointService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import com.drone.backend.config.JwtUtil;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;

import java.util.List;

@RestController
@RequiredArgsConstructor
@RequestMapping("/patrol-routes/{routeId}/waypoints")
public class WaypointController {

    private final WaypointService waypointService;
    private final JwtUtil jwtUtil;

    // 경로 포인트 등록 -> /waypoints/{routeId}
    @PutMapping
    public ResponseEntity<String> registerWaypoints(
            @PathVariable Long routeId,
            @RequestBody List<WaypointRequest> requestList,
            HttpServletRequest httpRequest
    ) {
        String token = jwtUtil.extractTokenFromRequest(httpRequest);
        if (token != null && jwtUtil.validateToken(token)) {
            // 순찰 경로는 팀 공용 자산이므로 지점 변경은 ADMIN만 허용한다.
            if (!"ADMIN".equals(jwtUtil.getRole(token))) {
                return ResponseEntity.status(HttpStatus.FORBIDDEN).body("경로 수정 권한이 없습니다. (관리자 전용)");
            }

            waypointService.registerWaypointList(routeId, requestList);
            return ResponseEntity.ok("경로 저장 완료");
        } else {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("로그인이 필요합니다.");
        }
    }

    // 경로 포인트 조회 -> /waypoints/{routeId}
    @GetMapping
    public ResponseEntity<?> getWaypoints(
            @PathVariable Long routeId,
            HttpServletRequest httpRequest) {

        String token = jwtUtil.extractTokenFromRequest(httpRequest);
        if (token == null || !jwtUtil.validateToken(token)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("로그인이 필요합니다.");
        }

        // 조회는 전원 공개 (OPERATOR도 순찰에 쓰려면 경로를 볼 수 있어야 한다)
        List<WaypointResponse> result = waypointService.getWaypointsByRouteId(routeId);
        return ResponseEntity.ok(result);
    }
}