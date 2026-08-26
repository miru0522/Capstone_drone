package com.drone.backend.controller;

// UserController.java

import com.drone.backend.config.JwtUtil;
import com.drone.backend.domain.User;
import com.drone.backend.dto.UserRequest;
import com.drone.backend.dto.UserResponse;
import com.drone.backend.repository.UserRepository;
import com.drone.backend.service.UserService;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;

@RestController
@RequestMapping
@RequiredArgsConstructor
public class UserController {

    private final UserService userService;

    private final JwtUtil jwtUtil;
    private final UserRepository userRepository;
    private final com.drone.backend.service.ProfileImageService profileImageService;

    /**
     * 프로필 사진 변경. multipart/form-data 의 image 파트로 받는다.
     * 응답의 profileImage 를 프론트가 그대로 <img src> 에 쓰면 된다.
     */
    @PutMapping(value = "/users/me/profile-image",
            consumes = org.springframework.http.MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<Map<String, String>> uploadProfileImage(
            @RequestParam("image") org.springframework.web.multipart.MultipartFile image,
            HttpServletRequest request) throws java.io.IOException {

        Long userId = jwtUtil.getId(jwtUtil.extractTokenFromRequest(request));
        String path = profileImageService.upload(userId, image);
        return ResponseEntity.ok(Map.of("profileImage", path));
    }

    /** 프로필 사진 제거 → 기본 아바타(하늘색 + 아이디)로 되돌아간다. */
    @DeleteMapping("/users/me/profile-image")
    public ResponseEntity<Map<String, String>> resetProfileImage(HttpServletRequest request) {
        Long userId = jwtUtil.getId(jwtUtil.extractTokenFromRequest(request));
        profileImageService.reset(userId);
        return ResponseEntity.ok(Map.of("message", "기본 프로필로 변경되었습니다."));
    }
    //회원가입 api /user/join
    @PostMapping("/auth/signup")
    public ResponseEntity<Map<String, String>> register(@RequestBody UserRequest.Join dto) {
        Map<String, String> response = new HashMap<>();
        try {
            userService.register(dto);
            response.put("message", "회원가입 성공");
            return ResponseEntity.ok(response);
        } catch (IllegalArgumentException e) {
            // 아이디 중복은 서버 오류가 아니라 입력 문제다.
            // 500으로 나가면 프론트가 원인을 구분할 수 없어 추측 문구를 띄우게 된다.
            // DroneController.registerDrone과 같은 관례(400 + 사유)로 맞춘다.
            response.put("message", e.getMessage());
            return ResponseEntity.badRequest().body(response);
        }
    }

    @org.springframework.beans.factory.annotation.Value("${jwt.expiration:86400000}")
    private long jwtExpiration;

    //로그인 api /user/login
    @PostMapping("/auth/login")
    public ResponseEntity<?> login(@RequestBody UserRequest.Login dto, HttpServletResponse response) {
        try {
            UserResponse.Login login = userService.login(dto);

            ResponseCookie cookie = ResponseCookie.from("jwtToken", login.getToken())
                    .httpOnly(true)
                    .secure(false) // HTTPS일 경우 true
                    .path("/")
                    .maxAge(jwtExpiration / 1000) // 밀리초 -> 초 변환
                    .build();
            // 응답에 Set-Cookie 헤더 추가
            response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());

            return ResponseEntity.ok(login);
        } catch (org.springframework.web.server.ResponseStatusException e) {
            // UserService에서 던진 401(비번 틀림) 혹은 403(승인 안됨)을 명확하게 반환
            return ResponseEntity.status(e.getStatusCode()).body(e.getReason());
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body("로그인 처리 중 에러가 발생했습니다.");
        }
    }
    //정보 불러오는 api /user/me
    @GetMapping("/users/me")
    public ResponseEntity<UserResponse.Info> getMyInfo(HttpServletRequest request) {
        String token = jwtUtil.extractTokenFromRequest(request);
        Long id = jwtUtil.getId(token);

        UserResponse.Info user = userService.getUserInfo(id);  // ID로 사용자 정보 조회
        return ResponseEntity.ok(user);
    }
    //계정 정보 수정 api /user/me
    //아이디 중복 확인 api /user/check-userId
    @GetMapping("/auth/check-id")
    public ResponseEntity<Map<String, Boolean>> checkUserIdDuplicate(@RequestParam String userId) {
        boolean exists = userService.checkUserIdExists(userId);
        Map<String, Boolean> result = new HashMap<>();
        result.put("exists", exists);
        return ResponseEntity.ok(result);
    }
    @PutMapping ("/users/me")
    public ResponseEntity<String> updateMyInfo(@RequestBody UserRequest.Update dto, HttpServletRequest request) {
        String token = jwtUtil.extractTokenFromRequest(request);
        Long id = jwtUtil.getId(token);
        User user = userRepository.findById(id).orElse(null);
        userService.updateUserInfo(user, dto);
        return ResponseEntity.ok("사용자 정보가 성공적으로 수정되었습니다.");
    }
    //계정 삭제 api /user/me
    @DeleteMapping("/users/me")
    public ResponseEntity<String> deleteMyAccount(HttpServletRequest request, HttpServletResponse response) {
        String token = jwtUtil.extractTokenFromRequest(request);
        Long userId = jwtUtil.getId(token);
        userService.deleteUser(userId);

        Cookie jwtCookie = new Cookie("jwtToken", null);
        jwtCookie.setHttpOnly(true);
        jwtCookie.setPath("/");
        jwtCookie.setMaxAge(0); // 쿠키 즉시 만료
        // 로그인(login)이 쿠키를 secure(false)로 심으므로 삭제도 동일해야 한다.
        // 현재 배포(http://203.249.90.3:8031)는 평문 HTTP라, secure=true로 내리면
        // 브라우저가 Set-Cookie 자체를 무시해 쿠키가 지워지지 않는다.
        // ★ HTTPS 전환 시에는 login/logout/deleteMyAccount 세 곳을 함께 true로 되돌릴 것.
        jwtCookie.setSecure(false);

        response.addCookie(jwtCookie); // 쿠키 삭제 적용
        return ResponseEntity.ok("계정이 성공적으로 삭제되었습니다.");
    }

    // UserController.java
    @PostMapping("/auth/verify-password")
    public ResponseEntity<Map<String, String>> verifyPassword(@RequestBody UserRequest.PasswordRequest request, HttpServletRequest httpRequest) {
        String token = jwtUtil.extractTokenFromRequest(httpRequest);
        Long id = jwtUtil.getId(token);

        boolean isValid = userService.verifyPassword(id, request.getPwd());
        if (isValid) {
            Map<String, String> response = new HashMap<>();
            response.put("message", "비밀번호 확인 완료");
            return ResponseEntity.ok(response);
        } else {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("error", "비밀번호가 일치하지 않습니다"));
        }
    }


    @PostMapping("/auth/logout")
    public ResponseEntity<Map<String, String>> logout(HttpServletResponse response) {
        // JWT 쿠키 삭제 (expires 설정)
        Cookie jwtCookie = new Cookie("jwtToken", null);
        jwtCookie.setHttpOnly(true);
        jwtCookie.setPath("/");
        jwtCookie.setMaxAge(0); // 쿠키 즉시 만료
        // 로그인 시 쿠키를 secure(false)로 심으므로 삭제도 동일해야 한다.
        // 현재 배포(http://203.249.90.3:8031)는 평문 HTTP라, secure=true로 내리면
        // 브라우저가 Set-Cookie 자체를 무시해 쿠키가 지워지지 않는다.
        // ★ HTTPS 전환 시에는 login/logout/deleteMyAccount 세 곳을 함께 true로 되돌릴 것.
        jwtCookie.setSecure(false);

        response.addCookie(jwtCookie); // 쿠키 삭제 적용

        Map<String, String> responseBody = new HashMap<>();
        responseBody.put("message", "로그아웃 성공");
        return ResponseEntity.ok(responseBody);
    }
}