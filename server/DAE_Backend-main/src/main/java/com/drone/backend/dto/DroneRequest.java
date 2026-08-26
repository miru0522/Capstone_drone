package com.drone.backend.dto;

import java.time.LocalDateTime;
import lombok.*;
import org.springframework.web.multipart.MultipartFile;

public class DroneRequest {
    @Getter
    @Setter
    @Data
    public static class Register{
        private String droneName;
        private String droneId;
        private MultipartFile droneImage;
        private LocalDateTime droneCheckdate;
    }

    @Getter
    @Setter
    @Data
    public static class Update{
        private String droneName;
        private LocalDateTime droneCheckdate;
    }

}
