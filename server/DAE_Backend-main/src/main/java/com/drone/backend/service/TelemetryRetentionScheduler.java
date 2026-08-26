package com.drone.backend.service;

import com.drone.backend.repository.TelemetryHistoryRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

@Service
@RequiredArgsConstructor
@Slf4j
@ConditionalOnProperty(name = "app.telemetry.retention.enabled", havingValue = "true")
public class TelemetryRetentionScheduler {

    private final TelemetryHistoryRepository repository;

    @Value("${app.telemetry.retention.days:90}")
    private int retentionDays;

    @Scheduled(cron = "0 0 3 * * ?") // 매일 새벽 3시
    @Transactional
    public void deleteOldTelemetryData() {
        log.info("🧹 텔레메트리 보존 주기({}일)에 따른 과거 데이터 정리 스케줄러 실행", retentionDays);
        LocalDateTime threshold = LocalDateTime.now().minusDays(retentionDays);
        
        try {
            int deletedCount = repository.deleteOlderThan(threshold);
            log.info("✅ 삭제 완료: {}건의 과거 텔레메트리 데이터가 정리되었습니다.", deletedCount);
        } catch (Exception e) {
            log.error("❌ 텔레메트리 정리 스케줄러 실행 중 오류 발생", e);
        }
    }
}
