package com.drone.backend.controller;

import com.drone.backend.domain.TelemetryHistory;
import com.drone.backend.dto.FlightSessionResponse;
import com.drone.backend.service.TelemetryHistoryService;
import lombok.RequiredArgsConstructor;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.List;

@RestController
@RequestMapping("/drones/{droneId}")
@RequiredArgsConstructor
public class TelemetryHistoryController {

    private final TelemetryHistoryService telemetryHistoryService;

    // 특정 드론의 비행 이력 조회
    // 예: GET /telemetry/history/DR-SIM?hours=24
    //     GET /telemetry/history/DR-SIM?from=2026-08-14T14:32:00&to=2026-08-14T14:51:00  (세션 상세)
    @GetMapping("/telemetry")
    public ResponseEntity<List<TelemetryHistory>> getHistory(
            @PathVariable String droneId,
            @RequestParam(required = false, defaultValue = "24") Integer hours,
            @RequestParam(required = false) String date,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime from,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime to) {

        List<TelemetryHistory> history = telemetryHistoryService.getHistoryByDroneId(droneId, hours, date, from, to);
        return ResponseEntity.ok(history);
    }

    // 비행 세션 목록 (Flight History 목록 뷰)
    // 예: GET /drones/DR-SIM/flights?from=2026-09-04T15:00:00&to=2026-09-11T15:00:00
    //     from/to 는 DB와 같은 UTC 기준. 없으면 기존 hours/date 규칙을 따른다.
    @GetMapping("/flights")
    public ResponseEntity<List<FlightSessionResponse>> getSessions(
            @PathVariable String droneId,
            @RequestParam(required = false, defaultValue = "24") Integer hours,
            @RequestParam(required = false) String date,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime from,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime to) {

        return ResponseEntity.ok(telemetryHistoryService.getSessions(droneId, hours, date, from, to));
    }
}
