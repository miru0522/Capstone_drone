package com.drone.backend.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.Getter;

public class UserResponse {

    @Getter
    @AllArgsConstructor
    @Data
    public static class Login {
        private String token;
    }

    @Getter @AllArgsConstructor
    public static class Info {
        private Long id;
        private String userId;
        private String name;
        private String email;
        private String role;
        private String status;
        /** 상대 URL. null이면 프론트가 기본 아바타(하늘색 + 아이디)를 렌더링한다. */
        private String profileImage;
    }
}