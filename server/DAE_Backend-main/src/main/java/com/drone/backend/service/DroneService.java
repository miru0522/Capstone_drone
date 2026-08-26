package com.drone.backend.service;


import com.drone.backend.domain.Drone;
import com.drone.backend.dto.DroneRequest;
import com.drone.backend.repository.DroneRepository;
import com.drone.backend.dto.DroneResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import jakarta.transaction.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

@Service
@RequiredArgsConstructor

public class DroneService {

    private final DroneRepository droneRepository;

    // 드론 등록
    public void registerDrone(DroneRequest.Register request) {
        // 드론 이름 중복 검사
        if (droneRepository.existsByDroneName(request.getDroneName())) {
            throw new IllegalArgumentException("이미 존재하는 드론 이름입니다.");
        }

        // 드론 번호 중복 검사
        if (droneRepository.existsByDroneId(request.getDroneId())) {
            throw new IllegalArgumentException("이미 존재하는 드론 번호입니다.");
        }

        MultipartFile image = request.getDroneImage();
        String filename = (image != null && !image.isEmpty()) ? image.getOriginalFilename() : "default.png";

        Drone drone = Drone.builder()
                .droneName(request.getDroneName())
                .droneId(request.getDroneId())
                .droneImage(filename)
                .droneCheckdate(
                        request.getDroneCheckdate() != null
                                ? request.getDroneCheckdate()
                                : null
                )
                .build();

        droneRepository.save(drone);
    }

    // 드론 조회 — 드론은 팀 공용 자산이므로 소유자와 무관하게 전부 보여준다.
    // (등록·수정·삭제는 ADMIN만 가능하므로 조회를 열어도 변경되지는 않는다)
    public List<DroneResponse.Search> getAllDrones() {
        List<Drone> droneList = droneRepository.findAll();

        return droneList.stream().map(drone ->
                new DroneResponse.Search(
                        drone.getDroneId(),
                        drone.getDroneName(),
                        drone.getDroneImage(),
                        drone.getDroneCheckdate(),
                        drone.getStationLat(),   // 신호가 없어도 홈 마커를 그리려면 필요하다
                        drone.getStationLng()
                )).toList();
    }

    // 특정 드론 정보 수정
    @Transactional
    public Drone updateDroneInfo(String droneId, DroneRequest.Update request) {
        Drone drone = droneRepository.findByDroneId(droneId)
                .orElseThrow(() -> new RuntimeException("드론을 찾을 수 없습니다."));

        // 드론이 공용이 되었으므로 이름도 전역으로 유일해야 한다.
        if (!drone.getDroneName().equals(request.getDroneName()) &&
                droneRepository.existsByDroneName(request.getDroneName())) {
            throw new RuntimeException("이미 존재하는 드론 이름입니다.");
        }

        drone.setDroneName(request.getDroneName());
        drone.setDroneCheckdate(request.getDroneCheckdate());

        return drone; // 변경 감지로 JPA가 자동 업데이트
    }

    /**
     * 서버가 지시한 경로를 기록한다. 텔레메트리로는 좌표가 올라오지 않으므로
     * 여기서 남기지 않으면 "이 드론이 무슨 경로를 들고 있나"에 아무도 답할 수 없다.
     * @param routeJson null이면 경로를 비운다(순찰 취소·비상 정지)
     */
    @Transactional
    public void saveLastRoute(String droneId, String routeJson) {
        droneRepository.findByDroneId(droneId).ifPresent(d -> d.setLastRoute(routeJson));
        // 등록되지 않은 드론이면 조용히 넘어간다 — 명령 자체는 STOMP로 이미 나갔다
    }

    public String getLastRoute(String droneId) {
        return droneRepository.findByDroneId(droneId)
                .map(Drone::getLastRoute)
                .orElse(null);
    }

    @Transactional
    public void saveStation(String droneId, Double lat, Double lng) {
        droneRepository.findByDroneId(droneId).ifPresent(d -> {
            d.setStationLat(lat);
            d.setStationLng(lng);
        });
    }

    // 드론 삭제 서비스
    // 삭제 권한(ADMIN)은 컨트롤러에서 이미 검사한다.
    @Transactional
    public void deleteDrone(String droneId) {
        Drone drone = droneRepository.findByDroneId(droneId)
                .orElseThrow(() -> new RuntimeException("드론을 찾을 수 없습니다."));

        droneRepository.delete(drone);
    }

}

