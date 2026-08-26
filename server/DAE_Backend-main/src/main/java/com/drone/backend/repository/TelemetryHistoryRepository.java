package com.drone.backend.repository;

import com.drone.backend.domain.TelemetryHistory;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.List;

import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface TelemetryHistoryRepository extends JpaRepository<TelemetryHistory, Long> {
    
    // 특정 드론의 특정 기간 동안의 텔레메트리 조회 (시간순)
    List<TelemetryHistory> findByDroneIdAndTimestampBetweenOrderByTimestampAsc(String droneId, LocalDateTime start, LocalDateTime end);
    
    @Modifying
    @Query("DELETE FROM TelemetryHistory t WHERE t.timestamp < :thresholdDate")
    int deleteOlderThan(@Param("thresholdDate") LocalDateTime thresholdDate);
}
