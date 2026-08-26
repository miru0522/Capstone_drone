package com.drone.backend.repository;

import com.drone.backend.domain.UserDroneSettings;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface UserDroneSettingsRepository extends JpaRepository<UserDroneSettings, Long> {
    List<UserDroneSettings> findByUserIdOrderBySortOrderAsc(String userId);
    Optional<UserDroneSettings> findByUserIdAndDroneId(String userId, String droneId);
    void deleteByUserId(String userId);
}
