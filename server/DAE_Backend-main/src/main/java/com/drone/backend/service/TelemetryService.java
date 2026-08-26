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

@Service
@RequiredArgsConstructor
public class TelemetryService {

    private final DroneRepository droneRepository;
    private final TelemetryHistoryRepository telemetryHistoryRepository;

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
                    // DB 저장 (위경도/배터리 정보가 있는 경우에만 유의미하게 저장)
                    if (lat != null && lon != null) {
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