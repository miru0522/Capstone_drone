package com.drone.backend.service;

import com.drone.backend.config.JwtUtil;
import com.drone.backend.dto.UserRequest;
import com.drone.backend.dto.UserResponse;
import com.drone.backend.repository.UserRepository;
import jakarta.transaction.Transactional;
import lombok.RequiredArgsConstructor;
import com.drone.backend.domain.User;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class UserService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;
    //회원가입
    @Transactional
    public void register(UserRequest.Join dto) {
        if (userRepository.existsByUserId(dto.getUserId())) {
            throw new IllegalArgumentException("이미 존재하는 사용자명입니다.");
        }
        User user = User.builder()
                .userId(dto.getUserId())
                .pwd(passwordEncoder.encode(dto.getPwd()))
                .email(dto.getEmail())
                .name(dto.getName())
                .build();
        userRepository.save(user);
    }
    //로그인
    public UserResponse.Login login(UserRequest.Login dto) {
        User user = userRepository.findByUserId(dto.getUserId())
                .orElseThrow(() -> new UsernameNotFoundException("사용자를 찾을 수 없습니다."));

        if (!passwordEncoder.matches(dto.getPwd(), user.getPwd())) {
            throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.UNAUTHORIZED, "비밀번호가 틀립니다.");
        }

        if (user.getStatus() != com.drone.backend.domain.Status.APPROVED) {
            throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.FORBIDDEN, "계정이 승인되지 않았거나 비활성화 상태입니다.");
        }

        String token = jwtUtil.generateToken(user.getId(), user.getName(), user.getRole().name());
        return new UserResponse.Login(token);
    }
    //정보 조회
    public UserResponse.Info getUserInfo(Long id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("사용자 없음"));
        return new UserResponse.Info(user.getId(), user.getUserId(), user.getName(), user.getEmail(),
                user.getRole().name(), user.getStatus().name(), user.getProfileImage());
    }
    //아이디 중복 확인
    public boolean checkUserIdExists(String userId) {
        return userRepository.existsByUserId(userId);
    }
    //정보 수정
    @Transactional
    public void updateUserInfo(User user, UserRequest.Update dto) {
        if (dto.getName() != null) user.setName(dto.getName());
        if (dto.getPwd() != null) user.setPwd(passwordEncoder.encode(dto.getPwd()));
        if (dto.getEmail() != null) user.setEmail(dto.getEmail());
        if (dto.getUserId() != null) user.setUserId(dto.getUserId());

        userRepository.save(user);
    }
    //삭제
    @Transactional
    public void deleteUser(Long id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("해당 사용자를 찾을 수 없습니다."));
        userRepository.delete(user);
    }
    //비밀번호 확인
    public boolean verifyPassword(Long id, String pwd) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("사용자 없음"));
        String encodedPassword = user.getPwd();
        if (pwd == null || encodedPassword == null) {
            throw new IllegalArgumentException("비밀번호는 null일 수 없습니다.");
        }
        return passwordEncoder.matches(pwd, encodedPassword);
    }
    
    //관리자 권한으로 타 사용자 비밀번호 강제 변경
    @Transactional
    public void changeUserPasswordByAdmin(Long id, String newPassword) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("해당 사용자를 찾을 수 없습니다."));
        user.setPwd(passwordEncoder.encode(newPassword));
        userRepository.save(user);
    }

    //관리자 권한으로 타 사용자 프로필 정보 일괄 변경
    @Transactional
    public void updateUserByAdmin(Long id, UserRequest.AdminUpdate dto) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("해당 사용자를 찾을 수 없습니다."));
        if (dto.getName() != null && !dto.getName().trim().isEmpty()) {
            user.setName(dto.getName());
        }
        if (dto.getEmail() != null && !dto.getEmail().trim().isEmpty()) {
            user.setEmail(dto.getEmail());
        }
        if (dto.getPwd() != null && !dto.getPwd().trim().isEmpty()) {
            user.setPwd(passwordEncoder.encode(dto.getPwd()));
        }
        userRepository.save(user);
    }
}