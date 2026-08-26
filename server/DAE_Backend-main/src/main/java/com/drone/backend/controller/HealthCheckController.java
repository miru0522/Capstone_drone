package com.drone.backend.controller;

import com.drone.backend.dto.UserResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.Map;

@RestController
@RequiredArgsConstructor
public class HealthCheckController {

    @GetMapping("/healthcheck")
    public ResponseEntity<Map<String, String>> healthcheck() {
        Map<String, String> response = new HashMap<>();
        response.put("message", "ok");
        return ResponseEntity.ok(response);
    }
}
