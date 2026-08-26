package com.drone.backend.dto;

import lombok.Data;
import lombok.Getter;
import lombok.Setter;


public class UserRequest {
    @Getter
    @Setter
    @Data
    public static class Join {
        private String userId;
        private String pwd;
        private String name;
        private String email;
    }
    @Getter
    @Setter
    @Data
    public static class Login {
        private String userId;
        private String pwd;
    }
    @Getter
    @Setter
    @Data
    public static class Update {
        private String userId;
        private String name;
        private String email;
        private String pwd;
    }
    @Getter
    @Setter
    public static class PasswordRequest {
        private String pwd;
    }

    @Getter
    @Setter
    @Data
    public static class AdminUpdate {
        private String name;
        private String email;
        private String pwd;
    }
}