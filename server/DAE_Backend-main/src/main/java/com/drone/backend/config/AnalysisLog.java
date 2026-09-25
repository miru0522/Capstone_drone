package com.drone.backend.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;

/** 관측 전용: 원문/예외 메시지/인증정보를 출력하지 않는다. */
public final class AnalysisLog {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final ThreadLocal<Context> CURRENT = new ThreadLocal<>();
    private static final String INSTANCE = UUID.randomUUID().toString();
    private static final AtomicLong DROPPED = new AtomicLong();
    private static final class Context {
        String id;
        Long eventId;
        final Map<String, String> states = new LinkedHashMap<>();
        final Map<String, Long> starts = new HashMap<>();
        Context(String id) {
            this.id = id;
            for (String stage : List.of("backend_receive", "backend_video_store", "backend_audio_store", "db_save", "alert_publish")) {
                states.put(stage, "not_attempted");
            }
        }
    }
    private AnalysisLog() {}

    public static void begin(String header) {
        boolean valid = header != null && header.matches("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");
        CURRENT.set(new Context(valid ? UUID.fromString(header).toString() : UUID.randomUUID().toString()));
        org.slf4j.MDC.put("analysis_id", CURRENT.get().id);
        emit("request", "started", Map.of("correlation_source", valid ? "ai_header" : "backend_generated",
                "invalid_correlation_header", header != null && !valid));
    }

    public static void clear() {
        CURRENT.remove();
        org.slf4j.MDC.remove("analysis_id");
    }

    public static void emit(String stage, String event, Map<String, ?> fields) {
        try {
            Context ctx = CURRENT.get();
            if (ctx == null) return;
            Map<String, Object> record = new LinkedHashMap<>();
            record.put("schema_version", "1.0");
            record.put("timestamp", Instant.now().toString());
            record.put("service", "backend");
            record.put("instance_id", INSTANCE);
            record.put("analysis_id", ctx.id);
            record.put("event_id", ctx.eventId);
            record.put("stage", stage);
            record.put("event", event);
            record.put("level", "failed".equals(event) ? "ERROR" : "INFO");
            record.put("dropped_logs", DROPPED.get());
            record.putAll(fields);
            System.out.println(JSON.writeValueAsString(record));
            if (System.out.checkError()) DROPPED.incrementAndGet();
        } catch (Exception ignored) {
            DROPPED.incrementAndGet();
        }
    }

    public static void start(String stage) {
        Context ctx = CURRENT.get();
        if (ctx != null) {
            ctx.states.put(stage, "started");
            ctx.starts.put(stage, System.nanoTime());
        }
        emit(stage, "started", Map.of());
    }

    public static void done(String stage, Map<String, ?> fields) {
        Context ctx = CURRENT.get();
        Map<String, Object> result = new LinkedHashMap<>(fields);
        if (ctx != null) {
            ctx.states.put(stage, "completed");
            Long start = ctx.starts.get(stage);
            if (start != null) result.put("duration_ms", (System.nanoTime() - start) / 1_000_000.0);
        }
        emit(stage, "completed", result);
    }

    public static void skip(String stage) {
        if (CURRENT.get() != null) CURRENT.get().states.put(stage, "skipped");
        emit(stage, "skipped", Map.of("reason_code", "no_audio"));
    }

    public static void saved(Long id) {
        if (CURRENT.get() != null) CURRENT.get().eventId = id;
    }

    public static void failed(Exception error) {
        Context ctx = CURRENT.get();
        if (ctx == null) return;
        String failed = "backend_receive";
        for (Map.Entry<String, String> entry : ctx.states.entrySet()) {
            if ("started".equals(entry.getValue())) failed = entry.getKey();
        }
        ctx.states.put(failed, "failed");
        // 소스 줄과 예외 메시지는 제외하고 스택 위치만 기록한다.
        List<Map<String, Object>> frames = new ArrayList<>();
        for (StackTraceElement frame : error.getStackTrace()) {
            if (frames.size() >= 12) break;
            frames.add(Map.of("class", frame.getClassName(), "method", frame.getMethodName(), "line", frame.getLineNumber()));
        }
        emit(failed, "failed", Map.of("error_type", error.getClass().getSimpleName(), "frames", frames));
    }

    public static void terminal(int status, long start) {
        Context ctx = CURRENT.get();
        if (ctx != null) {
            emit("request_terminal", status < 400 ? "completed" : "failed",
                    Map.of("response_status", status, "duration_ms", (System.nanoTime() - start) / 1_000_000.0,
                            "stages", ctx.states, "client_received", "unknown"));
        }
    }

    public static Map<String, Object> values(String drone, String label, Double vad, Double mae, String sourceKey) {
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("drone_id", drone != null && drone.matches("DR-[A-Za-z0-9_-]{1,32}") ? drone : null);
        values.put("label", List.of("정상", "폭력", "응급", "절도", "배회·침입").contains(label == null ? "" : label) ? label : null);
        values.put("vad_score", vad != null && Double.isFinite(vad) ? vad : null);
        values.put("mae_confidence", mae != null && Double.isFinite(mae) ? mae : null);
        values.put("vad_score_invalid", vad != null && !Double.isFinite(vad));
        values.put("mae_confidence_invalid", mae != null && !Double.isFinite(mae));
        values.put("source_key", sourceKey);
        return values;
    }
}
