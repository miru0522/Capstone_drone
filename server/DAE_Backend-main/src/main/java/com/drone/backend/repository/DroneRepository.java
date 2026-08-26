package com.drone.backend.repository;

import com.drone.backend.domain.Drone;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.*;

public interface DroneRepository extends JpaRepository<Drone, Long> {
    boolean existsByDroneId(String droneId);
    boolean existsByDroneName(String droneName);

    // 대리키(id) 조회는 JpaRepository.findById(Long)가 이미 제공한다.
    // 외부에서 드론을 가리키는 값은 업무키 droneId 하나뿐이다.
    Optional<Drone> findByDroneId(String droneId);
}

