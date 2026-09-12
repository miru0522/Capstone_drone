package com.drone.backend.service;

import com.drone.backend.repository.CommandLogRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

/**
 * 조작 이력 정리. <b>기본은 꺼져 있다.</b>
 *
 * 텔레메트리는 초당 한 건씩 쌓여 하루 8만 건이 넘으므로 90일로 자르지만,
 * 조작 이력은 하루 수십 건이라 자를 이유가 없다. "석 달 전에 누가 이 드론을
 * 착륙시켰나"를 못 찾는 것이 더 손해다.
 *
 * 필요해지면 app.command-log.retention.enabled=true 로 켠다.
 * 껍데기를 미리 두는 이유는, 나중에 급히 필요할 때 스케줄러부터 만들지
 * 않아도 되게 하려는 것이다(TelemetryRetentionScheduler 와 같은 형태).
 */
@Slf4j
@Service
@RequiredArgsConstructor
@ConditionalOnProperty(name = "app.command-log.retention.enabled", havingValue = "true")
public class CommandLogRetentionScheduler {

    private final CommandLogRepository repository;

    @Value("${app.command-log.retention.days:365}")
    private int retentionDays;

    // 텔레메트리(3시)·사고 파일(3시 15분) 정리와 겹치지 않게 한국 3시 30분
    @Scheduled(cron = "0 30 3 * * ?", zone = "Asia/Seoul")
    @Transactional
    public void deleteOld() {
        LocalDateTime threshold = LocalDateTime.now().minusDays(retentionDays);
        try {
            int deleted = repository.deleteOlderThan(threshold);
            log.info("🧹 조작 이력 {}일 보존 - {}건 정리", retentionDays, deleted);
        } catch (Exception e) {
            log.error("❌ 조작 이력 정리 중 오류", e);
        }
    }
}
