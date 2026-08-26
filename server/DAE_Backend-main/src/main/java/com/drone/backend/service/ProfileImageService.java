package com.drone.backend.service;

import com.drone.backend.domain.User;
import com.drone.backend.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

/**
 * 사용자 프로필 사진 업로드/삭제.
 *
 * 기본 프로필(하늘색 배경 + 아이디)은 <b>파일로 만들지 않는다.</b>
 * profileImage가 null이면 프론트가 그려주므로, 아이디가 바뀌어도 기본 아바타가 자동으로 따라가고
 * 계정마다 이미지를 생성·보관할 필요가 없다.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class ProfileImageService {

    private final UserRepository userRepository;

    @Value("${app.profile.storage-dir:./profiledata}")
    private String storageDir;

    /** 업로드 허용 확장자. 실행 가능한 파일이 올라오는 것을 막는다. */
    private static final Set<String> ALLOWED_EXT = Set.of("jpg", "jpeg", "png", "gif", "webp");
    private static final long MAX_BYTES = 5L * 1024 * 1024; // 5MB

    @Transactional
    public String upload(Long userId, MultipartFile file) throws IOException {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("유효하지 않은 사용자입니다."));

        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("업로드할 이미지가 없습니다.");
        }
        if (file.getSize() > MAX_BYTES) {
            throw new IllegalArgumentException("이미지는 5MB 이하만 올릴 수 있습니다.");
        }

        String ext = extensionOf(file.getOriginalFilename());
        if (!ALLOWED_EXT.contains(ext)) {
            throw new IllegalArgumentException("이미지 파일(jpg, png, gif, webp)만 올릴 수 있습니다.");
        }

        // 파일명은 서버가 정한다. 원본 이름을 그대로 쓰면 경로 조작(../)과 덮어쓰기 위험이 있다.
        String savedName = UUID.randomUUID() + "." + ext;
        Path dir = Paths.get(storageDir).toAbsolutePath().normalize();
        Files.createDirectories(dir);

        try (var in = file.getInputStream()) {
            Files.copy(in, dir.resolve(savedName), StandardCopyOption.REPLACE_EXISTING);
        }

        String previous = user.getProfileImage();
        user.setProfileImage("/profile/" + savedName);
        userRepository.save(user);

        deleteQuietly(previous); // 이전 사진은 지워 고아 파일이 쌓이지 않게 한다
        log.info("🖼️ 프로필 사진 변경 (userId={}, file={})", userId, savedName);

        return user.getProfileImage();
    }

    /** 기본 아바타로 되돌린다. */
    @Transactional
    public void reset(Long userId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("유효하지 않은 사용자입니다."));

        String previous = user.getProfileImage();
        user.setProfileImage(null);
        userRepository.save(user);

        deleteQuietly(previous);
        log.info("🖼️ 프로필 사진 초기화 (userId={})", userId);
    }

    private String extensionOf(String originalName) {
        if (originalName == null) {
            return "";
        }
        int dot = originalName.lastIndexOf('.');
        return dot < 0 ? "" : originalName.substring(dot + 1).toLowerCase(Locale.ROOT);
    }

    /** 파일 삭제 실패가 요청 자체를 실패시키면 안 되므로 로그만 남긴다. */
    private void deleteQuietly(String relativeUrl) {
        if (relativeUrl == null || !relativeUrl.startsWith("/profile/")) {
            return;
        }
        try {
            String name = relativeUrl.substring("/profile/".length());
            Files.deleteIfExists(Paths.get(storageDir).toAbsolutePath().normalize().resolve(name));
        } catch (Exception e) {
            log.warn("이전 프로필 사진 삭제 실패: {} ({})", relativeUrl, e.getMessage());
        }
    }
}
