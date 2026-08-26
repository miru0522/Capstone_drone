package com.drone.backend.repository;

import com.drone.backend.domain.User;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface UserRepository extends JpaRepository<User, Long> {
    Optional<User> findByUserId(String userId);
    Optional<User> findById(Long id);
    boolean existsByUserId(String userId);
    java.util.List<User> findByStatus(com.drone.backend.domain.Status status);

}