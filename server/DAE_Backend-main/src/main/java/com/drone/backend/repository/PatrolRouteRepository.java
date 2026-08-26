package com.drone.backend.repository;

import com.drone.backend.domain.PatrolRoute;
import org.springframework.data.jpa.repository.JpaRepository;


public interface PatrolRouteRepository extends JpaRepository<PatrolRoute, Long> {
    boolean existsByRouteName(String routeName);

}