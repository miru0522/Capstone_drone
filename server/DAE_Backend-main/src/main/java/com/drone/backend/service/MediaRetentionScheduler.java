package com.drone.backend.service;

import com.drone.backend.domain.EventLog;
import com.drone.backend.repository.EventLogRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.util.List;

/**
 * 사고 영상·음성 파일 정리.
 *
 * 보존 기간이 지난 사고의 <b>파일만</b> 지우고 경로를 비운다. 사고 기록(시각·점수·AI 설명·
 * 조치 상태)은 남긴다 — 행은 작고, "그때 무슨 일이 있었나"는 영상이 없어도 기록으로 남아야 한다.
 * 화면은 경로가 비었고 보존 기간이 지났으면 「보존 기간이 지나 삭제됨」으로 보인다.
 *
 * 파일을 지우지 못하면(디스크 오류 등) 경로를 남겨 다음 날 다시 시도한다.
 * 파일이 이미 없으면 경로만 비운다.
 */
@Slf4j
@Service
@RequiredArgsConstructor
@ConditionalOnProperty(name = "app.media.retention.enabled", havingValue = "true")
public class MediaRetentionScheduler {

    private final EventLogRepository repository;

    @Value("${app.media.retention.days:365}")
    private int retentionDays;

    // 텔레메트리(3시)와 겹치지 않게 한국 3시 15분
    @Scheduled(cron = "0 15 3 * * ?", zone = "Asia/Seoul")
    @Transactional
    public void purgeOldMedia() {
        // 사고 시각은 서버 시간(UTC)으로 저장되므로 기준도 서버 시간으로 잡는다
        LocalDateTime threshold = LocalDateTime.now().minusDays(retentionDays);
        try {
            List<EventLog> targets = repository.findWithMediaBefore(threshold);
            if (targets.isEmpty()) {
                log.info("🧹 사고 파일 {}일 보존 - 정리할 것 없음", retentionDays);
                return;
            }
            // 저장 위치는 EventController·TtsService 와 같다
            Path root = Paths.get(System.getProperty("user.dir"));
            int cleared = purge(targets, root.resolve("videodata"), root.resolve("wavdata"));
            // 트랜잭션 안의 엔티티라 경로를 비운 것은 커밋 때 반영된다
            log.info("🧹 사고 파일 {}일 보존 - 대상 {}건 중 {}건 정리", retentionDays, targets.size(), cleared);
        } catch (Exception e) {
            log.error("❌ 사고 파일 정리 중 오류", e);
        }
    }

    /**
     * 파일을 지우고 경로를 비운다. 지웠거나 원래 없던 것만 비운다.
     *
     * @return 경로를 하나라도 비운 사고 수
     */
    static int purge(List<EventLog> events, Path videoDir, Path audioDir) {
        int cleared = 0;
        for (EventLog e : events) {
            boolean changed = false;
            if (e.getVideoClipPath() != null && deleteInside(videoDir, e.getVideoClipPath())) {
                e.setVideoClipPath(null);
                changed = true;
            }
            if (e.getAudioFilePath() != null && deleteInside(audioDir, e.getAudioFilePath())) {
                e.setAudioFilePath(null);
                changed = true;
            }
            if (changed) cleared++;
        }
        return cleared;
    }

    /**
     * "/media/x.mp4" 같은 웹 경로에서 <b>파일 이름만</b> 떼어 dir 안에서 지운다.
     * 경로에 ".."이 섞여 있어도 dir 밖은 건드리지 않는다.
     *
     * @return 지웠거나 원래 없었으면 true, 지우지 못했으면 false
     */
    static boolean deleteInside(Path dir, String webPath) {
        Path name = Paths.get(webPath).getFileName();
        if (name == null) return true;
        try {
            Files.deleteIfExists(dir.resolve(name.toString()));
            return true;
        } catch (IOException ex) {
            log.warn("사고 파일 삭제 실패, 다음에 다시 시도: {} ({})", webPath, ex.toString());
            return false;
        }
    }
}
