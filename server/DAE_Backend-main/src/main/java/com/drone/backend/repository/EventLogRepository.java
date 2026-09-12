package com.drone.backend.repository;

import com.drone.backend.domain.EventLog;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;

@Repository
public interface EventLogRepository extends JpaRepository<EventLog, Long> {

    /** 최신순. 한쪽만 줘도 된다. */
    @Query("SELECT e FROM EventLog e "
            + "WHERE (:from IS NULL OR e.timestamp >= :from) "
            + "AND (:to IS NULL OR e.timestamp < :to) "
            + "ORDER BY e.eventId DESC")
    List<EventLog> search(@Param("from") LocalDateTime from, @Param("to") LocalDateTime to);

    /** 고른 드론들만. 최신순. 드론이 기록되지 않은 사고는 빠진다. */
    @Query("SELECT e FROM EventLog e "
            + "WHERE e.droneId IN :droneIds "
            + "AND (:from IS NULL OR e.timestamp >= :from) "
            + "AND (:to IS NULL OR e.timestamp < :to) "
            + "ORDER BY e.eventId DESC")
    List<EventLog> searchIn(@Param("droneIds") List<String> droneIds,
                            @Param("from") LocalDateTime from,
                            @Param("to") LocalDateTime to);

    /** 보존 기간이 지났는데 아직 파일이 남아 있는 사고. MediaRetentionScheduler 가 쓴다. */
    @Query("SELECT e FROM EventLog e WHERE e.timestamp < :threshold "
            + "AND (e.videoClipPath IS NOT NULL OR e.audioFilePath IS NOT NULL)")
    List<EventLog> findWithMediaBefore(@Param("threshold") LocalDateTime threshold);
}
