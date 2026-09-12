package com.drone.backend.repository;

import com.drone.backend.domain.CommandLog;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;

public interface CommandLogRepository extends JpaRepository<CommandLog, Long> {

    /** 최신순. 드론과 기간은 선택이며, 비우면 전체를 본다. */
    @Query("SELECT c FROM CommandLog c "
            + "WHERE (:droneId IS NULL OR c.droneId = :droneId) "
            + "AND (:from IS NULL OR c.timestamp >= :from) "
            + "AND (:to IS NULL OR c.timestamp < :to) "
            + "ORDER BY c.timestamp DESC")
    List<CommandLog> search(@Param("droneId") String droneId,
                            @Param("from") LocalDateTime from,
                            @Param("to") LocalDateTime to);

    /** 고른 드론들만. 최신순. */
    @Query("SELECT c FROM CommandLog c "
            + "WHERE c.droneId IN :droneIds "
            + "AND (:from IS NULL OR c.timestamp >= :from) "
            + "AND (:to IS NULL OR c.timestamp < :to) "
            + "ORDER BY c.timestamp DESC")
    List<CommandLog> searchIn(@Param("droneIds") List<String> droneIds,
                              @Param("from") LocalDateTime from,
                              @Param("to") LocalDateTime to);

    @Modifying
    @Query("DELETE FROM CommandLog c WHERE c.timestamp < :threshold")
    int deleteOlderThan(@Param("threshold") LocalDateTime threshold);
}
