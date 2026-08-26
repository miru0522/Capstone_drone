package com.drone.backend.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

/**
 * 지점의 지면 해발고도(m)를 조회한다. 구글 Elevation API를 쓴다.
 *
 * 이 값은 드론에게 <b>참고값</b>으로만 나간다(SET_ROUTE·SET_STATION의 ground_elevation_m).
 * 드론은 자체 센서로 실측한 AGL로 고도를 유지하므로, 이 값이 없어도 비행에 지장이 없다.
 * 2026-08-21 드론팀과 합의된 구조다.
 *
 * 그래서 이 서비스는 <b>절대 명령 전송을 막지 않는다</b>:
 *   · 키가 없으면 조용히 비운다 (설정 전에도 시스템이 돌아야 한다)
 *   · 호출이 실패하거나 느리면 비운다 (외부 API 때문에 순찰 지정이 막히면 안 된다)
 *
 * ⚠️ 지점마다 호출하지 말 것. 구글 Elevation은 한 요청에 여러 좌표를 받는다.
 *    예전 구현이 지점마다 왕복해서 경로 저장이 느렸다.
 */
@Service
@Slf4j
public class ElevationService {

    private static final String BASE_URL = "https://maps.googleapis.com/maps/api/elevation/json";
    /** 참고값을 얻자고 오래 기다릴 이유가 없다. 넘기면 그냥 비운다. */
    private static final int TIMEOUT_MS = 3000;
    /** 구글 권장 상한. 넘으면 나눠서 보낸다. */
    private static final int MAX_PER_REQUEST = 100;

    @Value("${google.maps.api-key:}")
    private String apiKey;

    private final RestTemplate restTemplate;
    private final ObjectMapper mapper = new ObjectMapper();

    public ElevationService() {
        SimpleClientHttpRequestFactory f = new SimpleClientHttpRequestFactory();
        f.setConnectTimeout(TIMEOUT_MS);
        f.setReadTimeout(TIMEOUT_MS);
        this.restTemplate = new RestTemplate(f);
    }

    /**
     * 여러 지점의 고도를 한 번에 조회한다.
     *
     * @param points {위도, 경도} 배열의 목록
     * @return 입력과 <b>같은 순서·같은 길이</b>의 목록. 모르는 값은 null.
     *         조회 자체가 실패하면 전부 null인 목록을 돌려준다(예외를 던지지 않는다).
     */
    public List<Double> getElevations(List<double[]> points) {
        List<Double> result = new ArrayList<>(Collections.nCopies(points.size(), null));
        if (points.isEmpty()) return result;

        if (apiKey == null || apiKey.isBlank()) {
            log.debug("고도 API 키가 없어 ground_elevation_m을 생략한다");
            return result;
        }

        for (int from = 0; from < points.size(); from += MAX_PER_REQUEST) {
            int to = Math.min(from + MAX_PER_REQUEST, points.size());
            List<double[]> chunk = points.subList(from, to);
            List<Double> got = requestChunk(chunk);
            for (int i = 0; i < got.size(); i++) result.set(from + i, got.get(i));
        }
        return result;
    }

    /** 지점 하나. 스테이션처럼 단일 좌표에 쓴다. */
    public Double getElevation(double lat, double lon) {
        return getElevations(List.of(new double[]{lat, lon})).get(0);
    }

    private List<Double> requestChunk(List<double[]> chunk) {
        List<Double> out = new ArrayList<>(Collections.nCopies(chunk.size(), null));
        String locations = chunk.stream()
                .map(p -> p[0] + "," + p[1])
                .collect(Collectors.joining("|"));
        try {
            String url = BASE_URL + "?locations=" + locations + "&key=" + apiKey;
            String json = restTemplate.getForObject(url, String.class);
            JsonNode root = mapper.readTree(json);
            String status = root.path("status").asText();
            if (!"OK".equals(status)) {
                // 키 제한·할당량 초과 등은 여기서 드러난다. 조용히 넘기지 않고 남긴다.
                log.warn("⚠️ 고도 조회 실패: status={} message={}",
                        status, root.path("error_message").asText(""));
                return out;
            }
            JsonNode results = root.path("results");
            for (int i = 0; i < results.size() && i < out.size(); i++) {
                JsonNode e = results.get(i).path("elevation");
                if (!e.isMissingNode()) out.set(i, e.asDouble());
            }
        } catch (Exception e) {
            // 참고값이므로 실패해도 명령은 그대로 나가야 한다.
            log.warn("⚠️ 고도 조회 중 오류(무시하고 계속): {}", e.getMessage());
        }
        return out;
    }
}
