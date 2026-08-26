package com.drone.backend.config;

import com.drone.backend.domain.Drone;
import com.drone.backend.domain.User;
import com.drone.backend.repository.DroneRepository;
import com.drone.backend.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;

import org.springframework.beans.factory.annotation.Value;
import com.drone.backend.domain.Role;
import com.drone.backend.domain.Status;

@Component
@RequiredArgsConstructor
public class DataInit implements CommandLineRunner {

    private final UserRepository userRepository;
    private final DroneRepository droneRepository;
    private final org.springframework.security.crypto.password.PasswordEncoder passwordEncoder;

    @Value("${ADMIN_ID:}")
    private String adminId;

    @Value("${ADMIN_PW:}")
    private String adminPw;

    @Override
    public void run(String... args) throws Exception {
        if (adminId == null || adminId.isBlank() || adminPw == null || adminPw.isBlank()) {
            System.out.println("⚠️ ADMIN_ID 또는 ADMIN_PW 환경 변수가 없어 시드 생성을 건너뜁니다.");
            return;
        }

        if (userRepository.existsByUserId(adminId)) {
            System.out.println("✅ 기존 관리자 계정(" + adminId + ")이 존재하여 시드 생성을 건너뜁니다.");
            return;
        }

        User admin = userRepository.save(User.builder()
                .userId(adminId)
                .pwd(passwordEncoder.encode(adminPw))
                .role(Role.ADMIN)
                .status(Status.APPROVED) // 승인 절차 없이 즉시 사용
                .name("관리자")
                .email("admin@lab.local")
                .build());

        seedDroneIfAbsent("DR-SIM", "가상 드론");

        System.out.println("✅ 초기 데이터 세팅 완료 (관리자: " + adminId + " / 드론: DR-SIM)");
    }

    private void seedDroneIfAbsent(String droneId, String droneName) {
        if (!droneRepository.existsByDroneId(droneId)) {
            droneRepository.save(Drone.builder()
                    .droneName(droneName)
                    .droneId(droneId)
                    .droneCheckdate(LocalDateTime.now())
                    .build());
        }
    }
}
