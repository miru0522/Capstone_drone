package com.drone.backend.controller;


import com.drone.backend.dto.DroneRequest;
import com.drone.backend.service.DroneService;
import com.drone.backend.service.ElevationService;
import com.drone.backend.dto.DroneResponse;
import com.drone.backend.domain.Drone;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import com.drone.backend.config.JwtUtil;
import jakarta.servlet.http.HttpServletRequest;

@RestController
@RequestMapping("/drones")
@RequiredArgsConstructor
@Slf4j
public class DroneController {

    private final DroneService droneService;
    private final ElevationService elevationService;
    private final JwtUtil jwtUtil;
    private final org.springframework.messaging.simp.SimpMessagingTemplate messagingTemplate;
    private final org.springframework.context.ApplicationEventPublisher eventPublisher;

    // 드론은 팀 공용 자산이다. 조회·조작은 전원, 등록·수정·삭제는 ADMIN만.
    // (순찰 명령은 관제사(OPERATOR)가 수행해야 하므로 막지 않는다)
    /** 관제사가 고도를 지정하지 않았을 때 쓰는 기본 순항고도(지면 기준). */
    private static final double DEFAULT_ALT_AGL_M = 50.0;

    private boolean isAdmin(String token) {
        return "ADMIN".equals(jwtUtil.getRole(token));
    }

    // 순찰 명령은 관제 업무다. ADMIN·OPERATOR가 수행하고 VIEWER는 조회만 한다.
    private boolean canOperate(String token) {
        String role = jwtUtil.getRole(token);
        return "ADMIN".equals(role) || "OPERATOR".equals(role);
    }

    /** 조작 권한 검사. 통과하면 null, 아니면 그대로 반환할 응답. */
    private ResponseEntity<String> denyIfCannotOperate(HttpServletRequest request) {
        String token = jwtUtil.extractTokenFromRequest(request);
        if (token == null || !jwtUtil.validateToken(token)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("로그인이 필요합니다.");
        }
        if (!canOperate(token)) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).body("드론 조작 권한이 없습니다. (조회 전용 계정)");
        }
        return null;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<String> registerDrone(
            @ModelAttribute DroneRequest.Register request,
            HttpServletRequest httpRequest) {

        String token = jwtUtil.extractTokenFromRequest(httpRequest);
        if (token == null || !jwtUtil.validateToken(token)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("로그인이 필요합니다.");
        }
        if (!isAdmin(token)) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).body("드론 등록 권한이 없습니다. (관리자 전용)");
        }
        try {
            droneService.registerDrone(request);
            return ResponseEntity.ok("드론이 등록되었습니다.");
        } catch(IllegalArgumentException e) {
            // 이름/번호 중복 등 입력 문제는 500이 아니라 400으로 구분해서 반환
            return ResponseEntity.badRequest().body(e.getMessage());
        } catch(Exception e) {
            log.error("드론 등록 에러: ", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body("등록 실패: " + e.getMessage());
        }
    }

    // 드론 조회 -> /drone/search
    @GetMapping
    public ResponseEntity<?> getDrones(HttpServletRequest httpRequest) {
        String token = jwtUtil.extractTokenFromRequest(httpRequest);
        if (token != null && jwtUtil.validateToken(token)) {
            return ResponseEntity.ok(droneService.getAllDrones());
        } else {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("로그인이 필요합니다.");
        }
    }

    // 특정 드론 수정 -> drones/{droneId}
    @PatchMapping("/{droneId}")
    public ResponseEntity<?> updateDrone(
            @PathVariable String droneId,
            @RequestBody DroneRequest.Update droneUpdate,
            HttpServletRequest httpRequest) {

        String token = jwtUtil.extractTokenFromRequest(httpRequest);

        if (token != null && jwtUtil.validateToken(token)) {
            if (!isAdmin(token)) {
                return ResponseEntity.status(HttpStatus.FORBIDDEN).body("드론 수정 권한이 없습니다. (관리자 전용)");
            }
            droneService.updateDroneInfo(droneId, droneUpdate);
            return ResponseEntity.ok("드론 정보가 수정되었습니다.");
        } else {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("로그인이 필요합니다.");
        }
    }

    // 특정 드론 삭제 -> /drone/{droneId}
    @DeleteMapping("/{droneId}")
    public ResponseEntity<?> deleteDrone(
            @PathVariable String droneId,
            HttpServletRequest httpRequest) {

        String token = jwtUtil.extractTokenFromRequest(httpRequest);

        if (token != null && jwtUtil.validateToken(token)) {
            if (!isAdmin(token)) {
                return ResponseEntity.status(HttpStatus.FORBIDDEN).body("드론 삭제 권한이 없습니다. (관리자 전용)");
            }
            try {
                droneService.deleteDrone(droneId);
                return ResponseEntity.ok("드론이 삭제되었습니다.");
            } catch (RuntimeException e) {
                return ResponseEntity.status(HttpStatus.NOT_FOUND).body(e.getMessage());
            }
        } else {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("로그인이 필요합니다.");
        }
    }

    // 1. 순찰 시작
    @PostMapping("/{droneId}/commands/start")
    public ResponseEntity<String> startPatrol(@PathVariable String droneId, HttpServletRequest httpRequest) {
        ResponseEntity<String> denied = denyIfCannotOperate(httpRequest);
        if (denied != null) return denied;

        log.info("🚀 {} 순찰 시작", droneId);

        java.util.Map<String, Object> command = new java.util.HashMap<>();
        command.put("action", "START_PATROL");
        command.put("droneId", droneId);
        messagingTemplate.convertAndSend("/topic/drones/" + droneId + "/commands", command);
        eventPublisher.publishEvent(new com.drone.backend.event.DroneCommandEvent(this, droneId, command));
        return ResponseEntity.ok("순찰을 시작했습니다.");
    }

    // 2. 순찰 재개
    @PostMapping("/{droneId}/commands/resume")
    public ResponseEntity<String> resumePatrol(@PathVariable String droneId, HttpServletRequest httpRequest) {
        ResponseEntity<String> denied = denyIfCannotOperate(httpRequest);
        if (denied != null) return denied;

        log.info("▶️ {} 순찰 재개", droneId);

        java.util.Map<String, Object> command = new java.util.HashMap<>();
        command.put("action", "RESUME_PATROL");
        command.put("droneId", droneId);
        messagingTemplate.convertAndSend("/topic/drones/" + droneId + "/commands", command);
        eventPublisher.publishEvent(new com.drone.backend.event.DroneCommandEvent(this, droneId, command));
        return ResponseEntity.ok("순찰을 재개했습니다.");
    }

    // 3. 순찰 취소 (경로 초기화 및 정지)
    @PostMapping("/{droneId}/commands/cancel")
    public ResponseEntity<String> cancelPatrol(@PathVariable String droneId, HttpServletRequest httpRequest) {
        ResponseEntity<String> denied = denyIfCannotOperate(httpRequest);
        if (denied != null) return denied;

        log.info("🛑 {} 순찰 취소", droneId);

        java.util.Map<String, Object> command = new java.util.HashMap<>();
        // 드론이 경로를 버리므로 서버 기록도 지운다.
        // 안 지우면 드론엔 없는데 화면엔 남는 상태가 된다.
        droneService.saveLastRoute(droneId, null);

        command.put("action", "CANCEL_PATROL");
        command.put("droneId", droneId);
        messagingTemplate.convertAndSend("/topic/drones/" + droneId + "/commands", command);
        eventPublisher.publishEvent(new com.drone.backend.event.DroneCommandEvent(this, droneId, command));
        return ResponseEntity.ok("순찰을 취소했습니다.");
    }

    // 4. 순찰 중지 (호버링)
    @PostMapping("/{droneId}/commands/pause")
    public ResponseEntity<String> pausePatrol(@PathVariable String droneId, HttpServletRequest httpRequest) {
        ResponseEntity<String> denied = denyIfCannotOperate(httpRequest);
        if (denied != null) return denied;

        log.info("⏸️ {} 일시 정지(호버링)", droneId);

        java.util.Map<String, Object> command = new java.util.HashMap<>();
        command.put("action", "PAUSE_PATROL");
        command.put("droneId", droneId);
        messagingTemplate.convertAndSend("/topic/drones/" + droneId + "/commands", command);
        eventPublisher.publishEvent(new com.drone.backend.event.DroneCommandEvent(this, droneId, command));
        return ResponseEntity.ok("순찰을 일시정지했습니다.");
    }

    // 5. 순찰 복귀
    @PostMapping("/{droneId}/commands/return")
    public ResponseEntity<String> returnToBase(@PathVariable String droneId, HttpServletRequest httpRequest) {
        ResponseEntity<String> denied = denyIfCannotOperate(httpRequest);
        if (denied != null) return denied;

        log.info("🏠 {} 순찰 복귀", droneId);

        java.util.Map<String, Object> command = new java.util.HashMap<>();
        command.put("action", "RETURN_TO_STATION");
        command.put("droneId", droneId);
        messagingTemplate.convertAndSend("/topic/drones/" + droneId + "/commands", command);
        eventPublisher.publishEvent(new com.drone.backend.event.DroneCommandEvent(this, droneId, command));
        return ResponseEntity.ok("스테이션으로 복귀합니다.");
    }

    // 6. 안전 착륙 (제자리 착륙)
    @PostMapping("/{droneId}/commands/land")
    public ResponseEntity<String> landPatrol(@PathVariable String droneId, HttpServletRequest httpRequest) {
        ResponseEntity<String> denied = denyIfCannotOperate(httpRequest);
        if (denied != null) return denied;

        log.info("🛬 {} 안전 착륙", droneId);
        
        java.util.Map<String, Object> command = new java.util.HashMap<>();
        command.put("action", "LAND");
        command.put("droneId", droneId);
        messagingTemplate.convertAndSend("/topic/drones/" + droneId + "/commands", command);
        eventPublisher.publishEvent(new com.drone.backend.event.DroneCommandEvent(this, droneId, command));
        return ResponseEntity.ok("현재 위치에 착륙합니다.");
    }

    // 7. 비상 착륙 (Emergency Land / Kill Switch)
    @PostMapping("/{droneId}/commands/emergency-stop")
    public ResponseEntity<String> emergencyStop(@PathVariable String droneId, HttpServletRequest httpRequest) {
        ResponseEntity<String> denied = denyIfCannotOperate(httpRequest);
        if (denied != null) return denied;

        log.info("🚨 {} 비상 착륙 (Kill Switch)", droneId);
        
        java.util.Map<String, Object> command = new java.util.HashMap<>();
        // 드론이 경로를 버리므로 서버 기록도 지운다.
        // 안 지우면 드론엔 없는데 화면엔 남는 상태가 된다.
        droneService.saveLastRoute(droneId, null);

        command.put("action", "EMERGENCY_STOP");
        command.put("droneId", droneId);
        messagingTemplate.convertAndSend("/topic/drones/" + droneId + "/commands", command);
        eventPublisher.publishEvent(new com.drone.backend.event.DroneCommandEvent(this, droneId, command));
        return ResponseEntity.ok("모터를 차단했습니다.");
    }

    // 시뮬레이터(테스트) 경로 설정
    @PutMapping("/{droneId}/route")
    public ResponseEntity<String> setRoute(@PathVariable String droneId, @RequestBody java.util.List<java.util.Map<String, Object>> waypoints, HttpServletRequest httpRequest) {
        ResponseEntity<String> denied = denyIfCannotOperate(httpRequest);
        if (denied != null) return denied;

        log.info("📍 {} 경로 지정 (총 {}개 지점)", droneId, waypoints == null ? 0 : waypoints.size());

        if (waypoints == null || waypoints.isEmpty()) {
            return ResponseEntity.badRequest().body("경로가 비어 있습니다.");
        }

        // 좌표가 없거나 숫자가 아니면 500이 아니라 원인이 보이는 400으로 돌려준다.
        //
        // [2026-08-20] 드론팀 합의로 페이로드가 바뀌었다.
        //   · 경도 키를 lng → lon 으로 통일한다 (텔레메트리의 lon_deg 와 맞춘다).
        //     프론트는 지도 라이브러리 관례상 lng를 쓰므로 여기서 둘 다 받아 흡수한다.
        //   · 지점마다 alt_agl(지면 기준 목표고도)을 함께 보낸다. AGL이 기준이다.
        //   · ground_elevation_m(지면 해발고도)은 서버가 아는 경우에만 참고로 싣는다.
        //     드론은 자체 센서로 AGL을 유지하고, 이 값은 사전 참고용으로만 쓴다.
        java.util.List<java.util.Map<String, Object>> route = new java.util.ArrayList<>();
        for (int i = 0; i < waypoints.size(); i++) {
            java.util.Map<String, Object> wp = waypoints.get(i);
            Double lat = toDouble(wp == null ? null : wp.get("lat"));
            Double lon = toDouble(wp == null ? null : wp.get("lon"));
            if (lon == null) lon = toDouble(wp == null ? null : wp.get("lng"));   // 프론트 호환
            if (lat == null || lon == null) {
                log.warn("⚠️ {} 경로 {}번째 지점 좌표 누락·형식 오류: {}", droneId, i, wp);
                return ResponseEntity.badRequest().body(
                        "경로 " + i + "번째 지점에 lat/lon이 없습니다. [{\"lat\":36.6,\"lon\":127.2}, ...] 형태로 보내주세요.");
            }
            java.util.Map<String, Object> point = new java.util.LinkedHashMap<>();
            point.put("lat", lat);
            point.put("lon", lon);
            // 지정이 없으면 기본 순항고도를 쓴다. 드론은 최소 안전고도(20m)를 자체 하한선으로 둔다.
            Double altAgl = toDouble(wp.get("alt_agl"));
            point.put("alt_agl", altAgl != null ? altAgl : DEFAULT_ALT_AGL_M);
            Double groundElev = toDouble(wp.get("ground_elevation_m"));
            if (groundElev != null) point.put("ground_elevation_m", groundElev);
            route.add(point);
        }

        // 지면 해발고도를 참고값으로 붙인다. 지점 전체를 한 번에 조회한다 —
        // 예전 구현은 지점마다 왕복해서 경로 저장이 느렸다.
        // 실패하거나 키가 없으면 이 필드만 빠진다. 순찰 지정은 그대로 진행된다.
        java.util.List<double[]> coords = new java.util.ArrayList<>();
        for (java.util.Map<String, Object> p : route) {
            coords.add(new double[]{(Double) p.get("lat"), (Double) p.get("lon")});
        }
        java.util.List<Double> elevations = elevationService.getElevations(coords);
        int gotElev = 0;
        for (int i = 0; i < route.size(); i++) {
            if (route.get(i).get("ground_elevation_m") == null && elevations.get(i) != null) {
                route.get(i).put("ground_elevation_m", elevations.get(i));
                gotElev++;
            }
        }
        log.info("⛰️ {} 지면고도 {}/{}개 조회됨", droneId, gotElev, route.size());

        // 서버가 지시한 경로를 기록한다. 이걸 남기지 않으면 나중에 아무도 알 수 없다
        // (텔레메트리에는 hasRoute 불리언만 올라온다).
        //
        // ⚠️ 받은 원본(waypoints)이 아니라 정규화한 route를 저장한다.
        //    원본을 그대로 넣으면 보낸 쪽이 lat/lng로 줬는지 lat/lon으로 줬는지에 따라
        //    저장 형식이 달라져, 나중에 읽는 쪽이 어느 키를 봐야 할지 알 수 없다.
        //    (실제로 순찰 시작 팝업의 경로 미리보기가 이것 때문에 비어 보였다)
        try {
            droneService.saveLastRoute(droneId, new com.fasterxml.jackson.databind.ObjectMapper()
                    .writeValueAsString(route));
        } catch (Exception e) {
            log.warn("⚠️ {} 경로 기록 실패(명령 전송은 계속한다): {}", droneId, e.getMessage());
        }

        java.util.Map<String, Object> command = new java.util.HashMap<>();
        command.put("action", "SET_ROUTE");
        command.put("droneId", droneId);
        command.put("route", route);
        messagingTemplate.convertAndSend("/topic/drones/" + droneId + "/commands", command);
        eventPublisher.publishEvent(new com.drone.backend.event.DroneCommandEvent(this, droneId, command));
        
        return ResponseEntity.ok("경로를 지정했습니다.");
    }

    // 서버가 이 드론에게 마지막으로 지시한 경로. 없으면 빈 배열.
    // ⚠️ 드론이 지금도 이 경로를 들고 있다는 보장은 아니다 — 실제 보유 여부는 텔레메트리의 hasRoute다.
    @GetMapping("/{droneId}/route")
    public ResponseEntity<?> getRoute(@PathVariable String droneId) {
        String json = droneService.getLastRoute(droneId);
        if (json == null || json.isBlank()) {
            return ResponseEntity.ok(java.util.Collections.emptyList());
        }
        try {
            return ResponseEntity.ok(new com.fasterxml.jackson.databind.ObjectMapper()
                    .readValue(json, java.util.List.class));
        } catch (Exception e) {
            log.warn("⚠️ {} 저장된 경로 파싱 실패: {}", droneId, e.getMessage());
            return ResponseEntity.ok(java.util.Collections.emptyList());
        }
    }

    // 스테이션(기지국) 좌표 지정 — 드론이 RETURN_TO_BASE에서 사용할 복귀 목표
    @PutMapping("/{droneId}/station")
    public ResponseEntity<String> setStation(@PathVariable String droneId, @RequestBody java.util.Map<String, Object> location, HttpServletRequest httpRequest) {
        ResponseEntity<String> denied = denyIfCannotOperate(httpRequest);
        if (denied != null) return denied;

        // 경도 키는 lon으로 통일했다(2026-08-21). 프론트는 지도 관례상 lng를 쓰므로 둘 다 받는다.
        Double lat = toDouble(location == null ? null : location.get("lat"));
        Double lon = toDouble(location == null ? null : location.get("lon"));
        if (lon == null) lon = toDouble(location == null ? null : location.get("lng"));

        if (lat == null || lon == null) {
            log.warn("⚠️ {} 스테이션 지정 실패 — 좌표 누락·형식 오류: {}", droneId, location);
            return ResponseEntity.badRequest().body(
                    "스테이션 좌표가 없습니다. {\"lat\":36.6,\"lon\":127.2} 형태로 보내주세요.");
        }

        java.util.Map<String, Object> safeLocation = new java.util.LinkedHashMap<>();
        safeLocation.put("lat", lat);
        safeLocation.put("lon", lon);
        // 스테이션은 드론이 실제로 내려앉는 지점이라 경로 지점보다 고도가 중요하다.
        // 여기도 참고값이며, 없으면 드론이 자체 센서로 착륙한다.
        Double stationElev = elevationService.getElevation(lat, lon);
        if (stationElev != null) safeLocation.put("ground_elevation_m", stationElev);

        droneService.saveStation(droneId, lat, lon);

        java.util.Map<String, Object> command = new java.util.HashMap<>();
        command.put("action", "SET_STATION");
        command.put("droneId", droneId);
        command.put("station", safeLocation);
        messagingTemplate.convertAndSend("/topic/drones/" + droneId + "/commands", command);
        eventPublisher.publishEvent(new com.drone.backend.event.DroneCommandEvent(this, droneId, command));

        log.info("🏠 {} 스테이션 지정: {}, {} (지면 {}m)", droneId, lat, lon, stationElev);
        return ResponseEntity.ok("스테이션을 지정했습니다.");
    }

    /**
     * JSON에서 온 좌표값을 Double로 안전하게 변환한다.
     * Jackson은 Map&lt;String,Object&gt;에 숫자를 Integer/Double 등으로 넣으므로 Number로 받고,
     * 문자열로 온 경우도 허용한다. 변환 불가·null이면 null을 돌려준다(호출부에서 400 처리).
     */
    private Double toDouble(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number number) {
            return number.doubleValue();
        }
        try {
            return Double.parseDouble(value.toString().trim());
        } catch (NumberFormatException e) {
            return null;
        }
    }

}