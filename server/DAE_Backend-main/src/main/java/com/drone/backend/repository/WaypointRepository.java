package com.drone.backend.repository;

import com.drone.backend.domain.Waypoint;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.*;

public interface WaypointRepository extends JpaRepository<Waypoint, Long> {

    List<Waypoint> findByPatrolRoute_IdOrderByStepAsc(Long routeId);  // step 기준 정렬

    void deleteByPatrolRoute_Id(Long routeId);
}
