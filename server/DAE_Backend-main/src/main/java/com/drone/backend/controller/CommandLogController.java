package com.drone.backend.controller;

import com.drone.backend.domain.CommandLog;
import com.drone.backend.repository.CommandLogRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 조작 이력 조회. 조회 전용이라 <b>VIEWER 도 볼 수 있다</b> — 드론이 팀 공용
 * 자산이라는 기존 원칙과 같은 기준이다(SecurityConfig 의 /command-logs 는
 * authenticated).
 *
 * 쓰기 경로는 없다. 이력은 명령을 보낼 때만 쌓인다.
 */
@RestController
@RequestMapping("/command-logs")
@RequiredArgsConstructor
public class CommandLogController {

    private final CommandLogRepository repository;

    /**
     * @param droneId  여러 개 줄 수 있다. 비우면 전체 드론
     * @param from, to 구간(DB와 같은 UTC 기준). 한쪽만 줘도 된다.
     *                 하루 단위로 보려면 화면이 한국 하루를 UTC 구간으로 바꿔 보낸다 -
     *                 서버가 날짜를 받아 자르면 UTC 하루가 되어 9시간 어긋난다.
     */
    @GetMapping
    public ResponseEntity<List<CommandLog>> list(
            @RequestParam(required = false) List<String> droneId,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime from,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime to) {

        // 드론을 여러 대 고를 수 있다(?droneId=A&droneId=B). 없으면 전체.
        List<String> drones = droneId == null ? List.of()
                : droneId.stream().filter(s -> s != null && !s.isBlank()).map(String::trim).toList();
        return ResponseEntity.ok(drones.isEmpty()
                ? repository.search(null, from, to)
                : repository.searchIn(drones, from, to));
    }
}
