package com.drone.backend.service;

import com.drone.backend.domain.TelemetryHistory;
import com.drone.backend.dto.FlightSessionResponse;
import com.drone.backend.repository.TelemetryHistoryRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class TelemetryHistoryService {

    private final TelemetryHistoryRepository telemetryHistoryRepository;

    /**
     * 비행 중으로 보는 상태.
     * ⚠️ 프론트 `utils/droneStatus.js`의 isAirborne()과 같은 목록이다. 한쪽만 고치면 어긋난다.
     */
    private static final java.util.Set<String> AIRBORNE =
            java.util.Set.of("PATROLLING", "PAUSED", "RETURNING", "LANDING");

    /** 조회 구간 계산. date > hours 순으로 우선한다. */
    private LocalDateTime[] resolveRange(Integer hours, String date) {
        if (date != null && !date.trim().isEmpty()) {
            try {
                java.time.LocalDate parsed = java.time.LocalDate.parse(date);
                return new LocalDateTime[]{ parsed.atStartOfDay(), parsed.atTime(java.time.LocalTime.MAX) };
            } catch (Exception ignored) {
                // 파싱 실패 시 아래 기본값으로 떨어진다
            }
        }
        LocalDateTime end = LocalDateTime.now();
        int safeHours = Math.max(1, Math.min(hours != null ? hours : 24, 168)); // 최대 7일
        return new LocalDateTime[]{ end.minusHours(safeHours), end };
    }

    /**
     * 비행 세션 목록. 지상 → 비행 전이에서 시작하고 비행 → 지상 전이에서 끝난다.
     *
     * 반드시 다운샘플링 "이전"의 원시 행으로 계산해야 한다. 상태 전이는 대개 제자리에서
     * 일어나므로(착륙 → IDLE) 5m 필터를 거치면 경계 지점이 사라진다.
     */
    public List<FlightSessionResponse> getSessions(String droneId, Integer hours, String date) {
        LocalDateTime[] range = resolveRange(hours, date);
        List<TelemetryHistory> rows = telemetryHistoryRepository
                .findByDroneIdAndTimestampBetweenOrderByTimestampAsc(droneId, range[0], range[1]);

        List<FlightSessionResponse> sessions = new java.util.ArrayList<>();
        List<TelemetryHistory> current = new java.util.ArrayList<>();

        for (TelemetryHistory row : rows) {
            // status가 null인 행(이 기능 도입 이전 데이터)은 지상으로 본다.
            // ⚠️ Set.of()는 null을 허용하지 않아 contains(null)이 NPE를 던진다. 가드가 필수다.
            if (row.getStatus() != null && AIRBORNE.contains(row.getStatus())) {
                current.add(row);
            } else if (!current.isEmpty()) {
                sessions.add(summarize(current, false));
                current = new java.util.ArrayList<>();
            }
        }
        // 구간 끝까지 착륙 기록이 없으면 진행 중인 비행으로 본다
        if (!current.isEmpty()) {
            sessions.add(summarize(current, true));
        }

        java.util.Collections.reverse(sessions); // 최신 비행이 위로
        return sessions;
    }

    /** 점이 1개뿐인 구간은 거리·고도가 무의미하지만 비행 자체는 있었으므로 버리지 않는다. */
    private FlightSessionResponse summarize(List<TelemetryHistory> points, boolean inProgress) {
        double distance = 0.0;
        Double maxAlt = null;

        for (int i = 0; i < points.size(); i++) {
            TelemetryHistory p = points.get(i);
            if (p.getAltitude() != null && (maxAlt == null || p.getAltitude() > maxAlt)) {
                maxAlt = p.getAltitude();
            }
            if (i > 0) {
                TelemetryHistory prev = points.get(i - 1);
                if (prev.getLatitude() != null && prev.getLongitude() != null
                        && p.getLatitude() != null && p.getLongitude() != null) {
                    distance += calculateDistance(prev.getLatitude(), prev.getLongitude(),
                                                  p.getLatitude(), p.getLongitude());
                }
            }
        }

        TelemetryHistory first = points.get(0);
        TelemetryHistory last = points.get(points.size() - 1);

        return new FlightSessionResponse(
                first.getTimestamp(), last.getTimestamp(), points.size(),
                Math.round(distance * 10) / 10.0,
                maxAlt, first.getBattery(), last.getBattery(), inProgress);
    }

    public List<TelemetryHistory> getHistoryByDroneId(String droneId, Integer hours, String date) {
        return getHistoryByDroneId(droneId, hours, date, null, null);
    }

    /** from/to가 주어지면 그 구간만 조회한다(세션 상세 보기). 아니면 기존 hours/date 규칙을 따른다. */
    public List<TelemetryHistory> getHistoryByDroneId(String droneId, Integer hours, String date,
                                                      LocalDateTime from, LocalDateTime to) {
        LocalDateTime start;
        LocalDateTime end;

        if (from != null && to != null) {
            start = from;
            end = to;
        } else {
            LocalDateTime[] range = resolveRange(hours, date);
            start = range[0];
            end = range[1];
        }

        List<TelemetryHistory> rawHistory = telemetryHistoryRepository.findByDroneIdAndTimestampBetweenOrderByTimestampAsc(droneId, start, end);

        if (rawHistory.size() <= 2) {
            return rawHistory;
        }

        // 거리 기반 필터링 (최소 5미터 간격)
        List<TelemetryHistory> sampled = new java.util.ArrayList<>();
        TelemetryHistory lastSaved = rawHistory.get(0);
        sampled.add(lastSaved);

        double MIN_DISTANCE_METERS = 5.0;

        for (int i = 1; i < rawHistory.size() - 1; i++) {
            TelemetryHistory current = rawHistory.get(i);
            double distance = calculateDistance(
                    lastSaved.getLatitude(), lastSaved.getLongitude(),
                    current.getLatitude(), current.getLongitude()
            );

            if (distance >= MIN_DISTANCE_METERS) {
                sampled.add(current);
                lastSaved = current;
            }
        }

        // 가장 최신 데이터는 누락되지 않도록 무조건 추가
        TelemetryHistory endPoint = rawHistory.get(rawHistory.size() - 1);
        if (sampled.get(sampled.size() - 1) != endPoint) {
            sampled.add(endPoint);
        }

        return sampled;
    }

    // Haversine 공식을 이용한 두 위경도 좌표 사이의 거리 계산 (단위: 미터)
    private double calculateDistance(double lat1, double lon1, double lat2, double lon2) {
        final int R = 6371000; // 지구 반지름 (미터)
        double latDistance = Math.toRadians(lat2 - lat1);
        double lonDistance = Math.toRadians(lon2 - lon1);
        double a = Math.sin(latDistance / 2) * Math.sin(latDistance / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(lonDistance / 2) * Math.sin(lonDistance / 2);
        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c; 
    }
}
