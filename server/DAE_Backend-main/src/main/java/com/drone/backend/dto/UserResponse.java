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
        /**
         * 가입 신청 시각. 승인 판단에 직접 쓰인다 - 오래 방치된 건을 먼저
         * 처리하려면 언제 신청했는지 알아야 한다.
         */
        private java.time.LocalDateTime createdAt;
        /** 거절 사유. 거절된 계정에만 값이 있다. */
        private String rejectReason;
    }
}