package com.drone.backend.service;

import com.drone.backend.domain.Drone;
import com.drone.backend.dto.ConnectionResponse;
import com.drone.backend.dto.Telemetry;
import com.drone.backend.repository.DroneRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import com.drone.backend.domain.TelemetryHistory;
import com.drone.backend.repository.TelemetryHistoryRepository;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

@Service
@RequiredArgsConstructor
public class TelemetryService {

    private final DroneRepository droneRepository;
    private final TelemetryHistoryRepository telemetryHistoryRepository;

    /**
     * 지상에서는 이 간격마다 한 번만 남긴다.
     *
     * 드론은 지상에서도 초당 1회 보고하는데, 그걸 다 남기면 하루 86,400행이 쌓인다
     * (2026-09-11 기준 전체 360만 행 중 97%가 지상 행). 그 행을 읽는 곳이 없다 —
     * 비행 목록은 비행 행과 "비행이 끝났다"는 지상 행 하나만, 비행 상세는 비행 행만 쓴다.
     * 오히려 비행 목록 조회가 그 행들을 다 훑느라 느려졌다.
     */
    private static final long GROUND_SAVE_INTERVAL_MS = 60_000;

    /** 비행 중으로 보는 상태. ⚠️ TelemetryHistoryService.AIRBORNE 와 같은 목록이다. */
    private static final Set<String> AIRBORNE = Set.of("PATROLLING", "PAUSED", "RETURNING", "LANDING");

    /** 드론별 마지막으로 저장한 상태와 시각. 재시작하면 비므로 그 뒤 첫 보고는 무조건 저장된다. */
    private final Map<String, LastSaved> lastSaved = new ConcurrentHashMap<>();

    private record LastSaved(String status, long at) {}

    /**
     * 비행 중이면 매번, 지상이면 상태가 바뀌었거나 60초가 지났을 때만.
     *
     * "비행 → 지상"으로 바뀐 순간의 행은 상태 변화로 반드시 남으므로, 비행 목록이
     * 비행과 비행 사이를 가르는 근거는 사라지지 않는다.
     */
    private boolean shouldSave(String droneId, String status) {
        long now = System.currentTimeMillis();
        LastSaved prev = lastSaved.get(droneId);
        // Set.of()는 contains(null)에서 NPE를 던진다
        boolean airborne = status != null && AIRBORNE.contains(status);
        boolean save = airborne
                || prev == null
                || !Objects.equals(prev.status(), status)
                || now - prev.at() >= GROUND_SAVE_INTERVAL_MS;
        if (save) {
            lastSaved.put(droneId, new LastSaved(status, now));
        }
        return save;
    }

    public ConnectionResponse verifyAndRespond(Telemetry telemetry) {
        if (telemetry == null || telemetry.droneId() == null) {
            return new ConnectionResponse(false, null, "droneId가 없습니다.",
                    null, null, null);
        }

        String incoming = String.valueOf(telemetry.droneId()).trim();

        Double lat = telemetry.gps() != null ? telemetry.gps().lat_deg() : null;
        Double lon = telemetry.gps() != null ? telemetry.gps().lon_deg() : null;
        Double alt = telemetry.gps() != null ? telemetry.gps().abs_alt_m() : null;
        Double battery = telemetry.battery() != null ? telemetry.battery().remaining_percent() : null;

        return droneRepository.findByDroneId(incoming)
                .map(d -> {
                    // DB 저장 (위경도가 있고, 저장 규칙에 맞을 때만)
                    if (lat != null && lon != null && shouldSave(d.getDroneId(), telemetry.status())) {
                        TelemetryHistory history = TelemetryHistory.builder()
                                .droneId(d.getDroneId())
                                .latitude(lat)
                                .longitude(lon)
                                .altitude(alt)
                                .battery(battery)
                                .status(telemetry.status())
                                .timestamp(LocalDateTime.now())
                                .build();
                        telemetryHistoryRepository.save(history);
                    }
                    return new ConnectionResponse(true, d.getDroneId(), "연결 완료", lat, lon, battery);
                })
                .orElseGet(() -> new ConnectionResponse(false, incoming,
                        "등록되지 않은 드론입니다.", lat, lon, battery));
    }
}