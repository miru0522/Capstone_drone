package com.drone.backend.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class UserDroneSettingsDto {
    private String droneId;
    private boolean isVisible;
    private int sortOrder;
}
