package com.drone.backend.service;

import com.drone.backend.config.JwtUtil;
import com.drone.backend.dto.UserRequest;
import com.drone.backend.dto.UserResponse;
import com.drone.backend.repository.UserRepository;
import jakarta.transaction.Transactional;
import lombok.RequiredArgsConstructor;
import com.drone.backend.domain.User;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class UserService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;
    /** 아이디 최대 길이. User.userId 컬럼(length=32)과 반드시 같아야 한다. */
    public static final int USER_ID_MAX = 32;

    //회원가입
    @Transactional
    public void register(UserRequest.Join dto) {
        // 화면에서도 막지만 서버가 다시 본다. 화면 검사는 우회할 수 있고,
        // 우회하면 DataIntegrityViolationException 이 500 으로 나가면서
        // insert 문과 컬럼 이름이 그대로 노출된다(실제로 그런 응답을 본 적 있다).
        String userId = dto.getUserId() == null ? "" : dto.getUserId().trim();
        if (userId.isEmpty()) {
            throw new IllegalArgumentException("아이디를 입력해 주세요.");
        }
        if (userId.length() > USER_ID_MAX) {
            throw new IllegalArgumentException("아이디는 " + USER_ID_MAX + "자 이내로 입력해 주세요.");
        }

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
        // 아이디가 없을 때와 비밀번호가 틀릴 때를 같은 응답으로 돌려준다.
        //
        // 예전에는 UsernameNotFoundException을 던져 컨트롤러의 마지막 catch에 걸렸고,
        // 아이디 오타 하나에 "로그인 처리 중 에러가 발생했습니다"(500)가 나갔다.
        // 관제사는 자기 오타인 줄 모르고 서버가 고장 났다고 생각하게 된다.
        //
        // 둘을 구분해 알려주면 어떤 아이디가 존재하는지 알아내는 데 쓸 수 있으므로
        // 보안상으로도 합치는 편이 낫다.
        User user = userRepository.findByUserId(dto.getUserId())
                .orElseThrow(() -> new org.springframework.web.server.ResponseStatusException(
                        org.springframework.http.HttpStatus.UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다."));

        if (!passwordEncoder.matches(dto.getPwd(), user.getPwd())) {
            throw new org.springframework.web.server.ResponseStatusException(
                    org.springframework.http.HttpStatus.UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다.");
        }

        // 상태별로 문구를 가른다. 한 문장으로 뭉치면 신청자가 계속 기다려야
        // 하는지(대기), 아닌지(거절)를 알 수 없다.
        if (user.getStatus() != com.drone.backend.domain.Status.APPROVED) {
            throw new org.springframework.web.server.ResponseStatusException(
                    org.springframework.http.HttpStatus.FORBIDDEN, loginBlockedMessage(user));
        }

        String token = jwtUtil.generateToken(user.getId(), user.getName(), user.getRole().name());
        return new UserResponse.Login(token);
    }
    //정보 조회
    public UserResponse.Info getUserInfo(Long id) {
        User user = userRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("사용자 없음"));
        return new UserResponse.Info(user.getId(), user.getUserId(), user.getName(), user.getEmail(),
                user.getRole().name(), user.getStatus().name(), user.getProfileImage(),
                user.getCreatedAt(), user.getRejectReason());
    }
    /** 로그인이 막힌 이유를 본인에게 알린다. 거절 사유는 관리자가 남긴 그대로 전달한다. */
    private String loginBlockedMessage(User user) {
        switch (user.getStatus()) {
            case PENDING:
                return "가입 승인 대기 중입니다. 관리자 승인 후 이용할 수 있습니다.";
            case REJECTED:
                return user.getRejectReason() == null
                        ? "가입이 반려되었습니다. 관리자에게 문의해 주세요."
                        : "가입이 반려되었습니다. 사유: " + user.getRejectReason();
            case DISABLED:
                // 관리자가 보관함으로 옮긴 계정. 지운 것이 아니라 되돌릴 수 있다.
                return user.getRejectReason() == null
                        ? "계정이 보관 처리되었습니다. 관리자에게 문의해 주세요."
                        : "계정이 보관 처리되었습니다. 사유: " + user.getRejectReason();
            default:
                return "로그인할 수 없는 계정입니다. 관리자에게 문의해 주세요.";
        }
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