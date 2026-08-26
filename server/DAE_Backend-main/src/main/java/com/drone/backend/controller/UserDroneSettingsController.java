package com.drone.backend.controller;

import com.drone.backend.dto.UserDroneSettingsDto;
import com.drone.backend.service.UserDroneSettingsService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/users/me/drone-settings")
@RequiredArgsConstructor
public class UserDroneSettingsController {

    private final UserDroneSettingsService settingsService;

    @GetMapping
    public ResponseEntity<List<UserDroneSettingsDto>> getSettings() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !auth.isAuthenticated() || "anonymousUser".equals(auth.getPrincipal())) {
            return ResponseEntity.status(401).build();
        }
        return ResponseEntity.ok(settingsService.getUserSettings(auth.getName()));
    }

    @PutMapping
    public ResponseEntity<String> updateSettings(@RequestBody List<UserDroneSettingsDto> settings) {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !auth.isAuthenticated() || "anonymousUser".equals(auth.getPrincipal())) {
            return ResponseEntity.status(401).build();
        }
        settingsService.updateUserSettings(auth.getName(), settings);
        return ResponseEntity.ok("설정을 저장했습니다.");
    }
}
