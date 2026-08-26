package com.drone.backend.service;

import com.drone.backend.domain.PatrolRoute;
import com.drone.backend.repository.PatrolRouteRepository;
import com.drone.backend.domain.Waypoint;
import com.drone.backend.repository.WaypointRepository;
import com.drone.backend.dto.WaypointRequest;
import com.drone.backend.dto.WaypointResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class WaypointService {

    private final WaypointRepository waypointRepository;
    private final PatrolRouteRepository patrolRouteRepository;

    // 경로 포인트 등록 (해당 경로의 지점 목록을 통째로 교체한다)
    @Transactional
    public void registerWaypointList(Long routeId, List<WaypointRequest> requestList) {
        PatrolRoute patrolRoute = patrolRouteRepository.findById(routeId)
                .orElseThrow(() -> new RuntimeException("해당 PatrolRoute 없음"));

        // 경로 수정 시 같은 step이 중복 적재되지 않도록 기존 지점을 먼저 비운다.
        waypointRepository.deleteByPatrolRoute_Id(routeId);
        waypointRepository.flush();

        for (WaypointRequest req : requestList) {
            // 지면 고도(groundAltitude)와 그에 기반한 targetAltitude는 외부 고도 API가 있어야 구한다.
            // 구글 Elevation API를 쓰고 있었으나 저장만 하고 읽는 곳이 없어 제거했다.
            // 값을 지어내지 않고 null(=아직 모름)로 둔다. 실기 연동 시 브이월드 등으로 채운다.
            //
            // flightAltitude는 지면 기준 정책값(AGL 50m)이라 외부 고도와 무관하다.
            Waypoint wp = Waypoint.builder()
                    .patrolRoute(patrolRoute)
                    .step(req.getStep())
                    .latitude(req.getLatitude())
                    .longitude(req.getLongitude())
                    .address(req.getAddress())
                    .groundAltitude(null)
                    .flightAltitude(50.0)
                    .targetAltitude(null)
                    .build();

            waypointRepository.save(wp);
        }

    }

    // 경로 포인트 조회
    public List<WaypointResponse> getWaypointsByRouteId(Long routeId) {
        List<Waypoint> waypointList = waypointRepository.findByPatrolRoute_IdOrderByStepAsc(routeId);
        return waypointList.stream()
                .map(wp -> new WaypointResponse(
                        wp.getStep(),
                        wp.getLatitude(),
                        wp.getLongitude(),
                        wp.getAddress()
                )).collect(Collectors.toList());
    }

}
