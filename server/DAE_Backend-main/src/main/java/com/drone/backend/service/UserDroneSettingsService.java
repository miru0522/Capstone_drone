package com.drone.backend.service;

import com.drone.backend.dto.UserDroneSettingsDto;
import com.drone.backend.domain.UserDroneSettings;
import com.drone.backend.repository.UserDroneSettingsRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class UserDroneSettingsService {

    private final UserDroneSettingsRepository settingsRepository;

    @Transactional(readOnly = true)
    public List<UserDroneSettingsDto> getUserSettings(String userId) {
        return settingsRepository.findByUserIdOrderBySortOrderAsc(userId).stream()
                .map(s -> new UserDroneSettingsDto(s.getDroneId(), s.isVisible(), s.getSortOrder()))
                .collect(Collectors.toList());
    }

    @Transactional
    public void updateUserSettings(String userId, List<UserDroneSettingsDto> dtoList) {
        // 기존 설정 삭제 후 새로 삽입 (간단한 Bulk 대체 방식)
        settingsRepository.deleteByUserId(userId);
        
        List<UserDroneSettings> newSettings = dtoList.stream()
                .map(dto -> UserDroneSettings.builder()
                        .userId(userId)
                        .droneId(dto.getDroneId())
                        .isVisible(dto.isVisible())
                        .sortOrder(dto.getSortOrder())
                        .build())
                .collect(Collectors.toList());
                
        settingsRepository.saveAll(newSettings);
    }
}
