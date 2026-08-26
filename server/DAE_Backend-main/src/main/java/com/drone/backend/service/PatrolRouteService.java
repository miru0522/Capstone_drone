package com.drone.backend.service;

import com.drone.backend.domain.PatrolRoute;
import com.drone.backend.repository.PatrolRouteRepository;
import com.drone.backend.dto.PatrolRouteRequest;
import com.drone.backend.dto.PatrolRouteResponse;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import lombok.RequiredArgsConstructor;

import java.util.*;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class PatrolRouteService {

    private final PatrolRouteRepository patrolRouteRepository;

    // 경로 (이름, 설명) 등록
    public Long registerPatrolRoute(PatrolRouteRequest.Register request){
        // 경로는 팀 공용이므로 이름도 전역으로 유일해야 한다.
        // 사용자별 검사로 두면 같은 이름이 목록에 여러 개 떠서 고를 수 없다.
        if (patrolRouteRepository.existsByRouteName(request.getRouteName())) {
            throw new IllegalArgumentException("이미 존재하는 경로 이름입니다.");
        }

        PatrolRoute patrolRoute = PatrolRoute.builder()
                .routeName(request.getRouteName())
                .routeComment(request.getRouteComment())
                .build();

        PatrolRoute savedPatrolRoute = patrolRouteRepository.save(patrolRoute);
        return savedPatrolRoute.getId(); // 생성된 routeId 반환
    }

    // 경로 이름 중복 확인 (전역)
    public boolean isRouteNameDuplicate(String routeName) {
        return patrolRouteRepository.existsByRouteName(routeName);
    }

    // 경로 이름·설명 수정. 권한(ADMIN)은 컨트롤러에서 검사한다.
    @Transactional
    public void updatePatrolRoute(Long routeId, PatrolRouteRequest.Update request) {
        PatrolRoute patrolRoute = patrolRouteRepository.findById(routeId)
                .orElseThrow(() -> new IllegalArgumentException("해당 경로를 찾을 수 없습니다."));

        // ⚠️ 이름이 바뀐 경우에만 중복 검사한다.
        //    무조건 검사하면 설명만 고칠 때 "자기 이름"과 충돌한다고 거부당한다.
        if (!patrolRoute.getRouteName().equals(request.getRouteName())
                && patrolRouteRepository.existsByRouteName(request.getRouteName())) {
            throw new IllegalArgumentException("이미 존재하는 경로 이름입니다.");
        }

        patrolRoute.setRouteName(request.getRouteName());
        patrolRoute.setRouteComment(request.getRouteComment());
        // 변경 감지로 JPA가 자동 반영한다
    }

    // 경로 조회 — 순찰 경로는 팀 공용 자산이므로 소유자와 무관하게 전부 보여준다.
    // (생성·수정·삭제는 ADMIN만 가능하므로 조회를 열어도 변경되지는 않는다)
    public List<PatrolRouteResponse.Search> getAllPatrolRoutes() {
        List<PatrolRoute> patrolRouteList = patrolRouteRepository.findAll();

        // Java 16+ : .toList(), 그 이하 버전이면 Collectors.toList() 사용
        return patrolRouteList.stream()
                .map(patrolRoute -> new PatrolRouteResponse.Search(
                        patrolRoute.getId(),           // ★ 추가: routeId
                        patrolRoute.getRouteName(),
                        patrolRoute.getRouteComment()
                ))
                .toList();
        // 만약 Java 11 등이라면:
        // .collect(Collectors.toList());
    }

    // 경로 삭제
    // 삭제 권한(ADMIN)은 컨트롤러에서 이미 검사한다. 여기서는 존재 여부만 본다.
    public boolean deletePatrolRoute(Long routeId) {
        Optional<PatrolRoute> patrolRouteOpt = patrolRouteRepository.findById(routeId);
        if (patrolRouteOpt.isEmpty()) return false;

        PatrolRoute patrolRoute = patrolRouteOpt.get();

        // PatrolRoute.waypoints에 cascade=ALL + orphanRemoval이 걸려 있어 지점도 함께 삭제된다.
        // (DB의 ON DELETE CASCADE가 아니라 JPA 레벨 cascade다)
        patrolRouteRepository.delete(patrolRoute);
        return true;
    }
}
