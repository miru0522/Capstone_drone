package com.drone.backend.controller;

import com.drone.backend.domain.Role;
import com.drone.backend.domain.Status;
import com.drone.backend.domain.User;
import com.drone.backend.dto.UserResponse;
import com.drone.backend.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@RestController
@RequestMapping("/admin/users")
@RequiredArgsConstructor
@Slf4j
public class AdminController {

    private final UserRepository userRepository;
    private final com.drone.backend.service.UserService userService;

    @GetMapping
    public ResponseEntity<List<UserResponse.Info>> getUsers(@RequestParam(required = false) Status status) {
        List<User> users;
        if (status != null) {
            users = userRepository.findByStatus(status);
        } else {
            users = userRepository.findAll();
        }
        
        List<UserResponse.Info> dtos = users.stream()
            .map(u -> new UserResponse.Info(u.getId(), u.getUserId(), u.getName(), u.getEmail(),
                    u.getRole().name(), u.getStatus().name(), u.getProfileImage(),
                    u.getCreatedAt(), u.getRejectReason()))
            .collect(Collectors.toList());
            
        return ResponseEntity.ok(dtos);
    }

    @PostMapping("/{id}/approve")
    public ResponseEntity<String> approveUser(@PathVariable Long id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));
        user.setStatus(Status.APPROVED);
        // 거절했다가 다시 승인하는 경우가 있다. 옛 사유가 남아 있으면
        // 나중에 다시 거절할 때 그 문구가 되살아난다.
        user.setRejectReason(null);
        userRepository.save(user);
        log.info("관리자가 사용자({}) 가입을 승인했습니다.", user.getUserId());
        return ResponseEntity.ok("승인 완료");
    }

    /**
     * 가입 반려. 사유는 선택이며, 본인이 로그인을 시도하면 그 문구를 보여준다.
     *
     * 본문이 없어도 동작해야 한다 - 옛 화면이나 curl 에서 사유 없이 부를 수 있다.
     */
    @PostMapping("/{id}/reject")
    public ResponseEntity<String> rejectUser(
            @PathVariable Long id,
            @RequestBody(required = false) com.drone.backend.dto.UserRequest.Reject payload) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));
        user.setStatus(Status.REJECTED);

        String reason = payload == null ? null : payload.getReason();
        user.setRejectReason(reason == null || reason.isBlank() ? null : reason.trim());

        userRepository.save(user);
        log.info("관리자가 사용자({}) 가입을 반려했습니다. 사유={}", user.getUserId(),
                user.getRejectReason() == null ? "(없음)" : user.getRejectReason());
        return ResponseEntity.ok("거절 완료");
    }

    /**
     * 보관함으로 옮긴다. 지우는 것이 아니라 되돌릴 수 있다.
     *
     * 멀쩡히 쓰던 계정을 내리는 것이므로 사유를 남긴다 - 없으면 나중에 왜
     * 내렸는지 아무도 모른다. 반려와 같은 컬럼(reject_reason)을 쓴다.
     */
    @PostMapping("/{id}/disable")
    public ResponseEntity<String> disableUser(
            @PathVariable Long id,
            @RequestBody(required = false) com.drone.backend.dto.UserRequest.Reject payload) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));
        user.setStatus(Status.DISABLED);

        String reason = payload == null ? null : payload.getReason();
        user.setRejectReason(reason == null || reason.isBlank() ? null : reason.trim());

        userRepository.save(user);
        log.info("관리자가 사용자({})를 보관 처리했습니다. 사유={}", user.getUserId(),
                user.getRejectReason() == null ? "(없음)" : user.getRejectReason());
        return ResponseEntity.ok("보관 완료");
    }

    @PatchMapping("/{id}/role")
    public ResponseEntity<String> changeRole(@PathVariable Long id, @RequestBody Map<String, String> payload) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("사용자를 찾을 수 없습니다."));
        
        String newRoleStr = payload.get("role");
        if (newRoleStr != null) {
            try {
                Role newRole = Role.valueOf(newRoleStr.toUpperCase());
                user.setRole(newRole);
                userRepository.save(user);
                log.info("관리자가 사용자({})의 역할을 {}로 변경했습니다.", user.getUserId(), newRole);
                return ResponseEntity.ok("역할 변경 완료");
            } catch (IllegalArgumentException e) {
                return ResponseEntity.badRequest().body("잘못된 역할입니다.");
            }
        }
        return ResponseEntity.badRequest().body("role 필드가 필요합니다.");
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<String> deleteUser(@PathVariable Long id) {
        userService.deleteUser(id);
        log.info("관리자가 사용자(ID:{})를 영구 삭제했습니다.", id);
        return ResponseEntity.ok("계정 삭제 완료");
    }

    @PatchMapping("/{id}/password")
    public ResponseEntity<String> changePassword(@PathVariable Long id, @RequestBody Map<String, String> payload) {
        String newPassword = payload.get("pwd");
        if (newPassword == null || newPassword.trim().isEmpty()) {
            return ResponseEntity.badRequest().body("새 비밀번호가 필요합니다.");
        }
        userService.changeUserPasswordByAdmin(id, newPassword);
        log.info("관리자가 사용자(ID:{})의 비밀번호를 강제 변경했습니다.", id);
        return ResponseEntity.ok("비밀번호 변경 완료");
    }

    @PutMapping("/{id}/profile")
    public ResponseEntity<String> updateUserProfile(@PathVariable Long id, @RequestBody com.drone.backend.dto.UserRequest.AdminUpdate payload) {
        userService.updateUserByAdmin(id, payload);
        log.info("관리자가 사용자(ID:{})의 프로필을 변경했습니다.", id);
        return ResponseEntity.ok("프로필 정보 변경 완료");
    }
}
