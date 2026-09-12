package com.drone.backend.service;

import com.drone.backend.domain.Drone;
import com.drone.backend.repository.DroneRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 드론이 잊은 경로·스테이션을 다시 내려보낸다.
 *
 * 드론은 경로와 스테이션을 메모리에만 들고 있어 재부팅하면 잊는다. 그런데 서버는
 * SET_ROUTE·SET_STATION을 관제사가 저장할 때만 보냈다(DroneController). 그래서
 * 재부팅한 드론에 「순찰 복귀」를 눌러도 조용히 아무 일도 일어나지 않았고,
 * <b>배터리 40% 자율복귀는 갈 곳을 잃었다</b> — 페일세이프가 무력해진다.
 *
 * 관제사는 이를 알 수 없다. 화면에 보이는 스테이션은 DB에서 읽은 값이라
 * "있음"으로 보이지만 드론은 모르고 있다.
 *
 * DB에 원본이 있으므로(lastRoute, stationLat/Lng) 서버가 다시 알려주면 끝난다.
 * 드론 쪽 수정이 필요 없다.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class DroneStateSyncService {

    /** 이 시간 이상 텔레메트리가 끊겼으면 재부팅·재접속으로 본다 */
    private static final long GAP_MS = 15_000;

    private final DroneRepository droneRepository;
    private final SimpMessagingTemplate messagingTemplate;
    private final ObjectMapper mapper = new ObjectMapper();

    /** 같은 드론에 재전송을 이 간격보다 촘촘히 하지 않는다 */
    private static final long RESEND_COOLDOWN_MS = 10_000;

    /** droneId → 마지막 텔레메트리 수신 시각 */
    private final Map<String, Long> lastSeen = new ConcurrentHashMap<>();
    /** droneId → 마지막 재전송 시각 */
    private final Map<String, Long> lastResend = new ConcurrentHashMap<>();

    /**
     * 텔레메트리를 받을 때마다 호출한다. 필요할 때만 명령을 보낸다.
     *
     * @param hasRoute 드론이 신고한 경로 보유 여부. 안 보내면 null
     */
    public void syncIfNeeded(String droneId, Boolean hasRoute) {
        long now = System.currentTimeMillis();
        Long prev = lastSeen.put(droneId, now);

        // 공백이 있었으면 재부팅으로 보고 둘 다 다시 보낸다.
        // 스테이션은 드론이 보유 여부를 알려주지 않아 이 방법밖에 없다.
        boolean afterGap = (prev == null) || (now - prev > GAP_MS);

        // 드론이 경로가 없다고 신고했는데 DB에는 있다 — 추측이 아니라 확실한 불일치다.
        // 재부팅이 빨라 공백이 안 잡히는 경우를 이것이 잡는다.
        boolean routeMismatch = Boolean.FALSE.equals(hasRoute);

        if (!afterGap && !routeMismatch) return;

        // 드론이 명령을 적용하지 못하면 hasRoute가 계속 false로 온다.
        // 쿨다운이 없으면 텔레메트리 주기(1초)마다 같은 명령이 나간다.
        Long sentAt = lastResend.get(droneId);
        if (sentAt != null && now - sentAt < RESEND_COOLDOWN_MS) return;

        droneRepository.findByDroneId(droneId).ifPresent(d -> {
            lastResend.put(droneId, now);
            resendRoute(d);
            // 스테이션은 공백 뒤에만 보낸다. 경로 불일치는 스테이션과 무관하다.
            if (afterGap) resendStation(d);
        });
    }

    private void resendRoute(Drone d) {
        String json = d.getLastRoute();
        if (json == null || json.isBlank()) return;
        try {
            // lastRoute는 드론에 보낸 정규화 형식 그대로다(lat/lon/alt_agl/ground_elevation_m).
            // 지면고도를 다시 조회하지 않는다 — 외부 API 호출을 늘릴 이유가 없다.
            List<Map<String, Object>> route = mapper.readValue(json, List.class);
            if (route.isEmpty()) return;

            Map<String, Object> command = new HashMap<>();
            command.put("action", "SET_ROUTE");
            command.put("droneId", d.getDroneId());
            command.put("route", route);
            send(d.getDroneId(), command);
            log.info("🔄 {} 경로 재전송 ({}개 지점) — 드론이 잊었거나 재접속", d.getDroneId(), route.size());
        } catch (Exception e) {
            log.warn("경로 재전송 실패 {}: {}", d.getDroneId(), e.getMessage());
        }
    }

    private void resendStation(Drone d) {
        if (d.getStationLat() == null || d.getStationLng() == null) return;

        Map<String, Object> station = new HashMap<>();
        station.put("lat", d.getStationLat());
        station.put("lon", d.getStationLng());   // 드론에 나가는 키는 항상 lon

        Map<String, Object> command = new HashMap<>();
        command.put("action", "SET_STATION");
        command.put("droneId", d.getDroneId());
        command.put("station", station);
        send(d.getDroneId(), command);
        log.info("🔄 {} 스테이션 재전송 ({}, {})", d.getDroneId(), d.getStationLat(), d.getStationLng());
    }

    private void send(String droneId, Map<String, Object> command) {
        messagingTemplate.convertAndSend("/topic/drones/" + droneId + "/commands", command);
    }
}
