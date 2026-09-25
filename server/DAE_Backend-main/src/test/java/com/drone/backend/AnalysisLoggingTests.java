package com.drone.backend;

import com.drone.backend.config.AnalysisLog;
import com.drone.backend.config.AnalysisLogFilter;
import com.drone.backend.controller.EventController;
import com.drone.backend.domain.EventLog;
import com.drone.backend.repository.DroneRepository;
import com.drone.backend.repository.EventLogRepository;
import com.drone.backend.service.TtsService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.web.multipart.MultipartFile;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class AnalysisLoggingTests {
    @TempDir Path temp;
    final ObjectMapper json = new ObjectMapper();
    ByteArrayOutputStream bytes;
    PrintStream previous;
    String userDir;
    EventLogRepository repository;
    SimpMessagingTemplate messages;
    EventController controller;
    MultipartFile video;

    @BeforeEach void setup() {
        previous = System.out;
        bytes = new ByteArrayOutputStream();
        System.setOut(new PrintStream(bytes, true, StandardCharsets.UTF_8));
        userDir = System.getProperty("user.dir");
        System.setProperty("user.dir", temp.toString());
        repository = mock(EventLogRepository.class);
        DroneRepository drones = mock(DroneRepository.class);
        when(drones.existsByDroneId("DR-01")).thenReturn(true);
        when(repository.save(any())).thenAnswer(invocation -> {
            EventLog event = invocation.getArgument(0);
            event.setEventId(17L);
            return event;
        });
        messages = mock(SimpMessagingTemplate.class);
        controller = new EventController(repository, drones, mock(TtsService.class), messages);
        video = mock(MultipartFile.class);
        when(video.getOriginalFilename()).thenReturn("test.mp4");
        when(video.getSize()).thenReturn(100L);
    }

    @AfterEach void cleanup() {
        AnalysisLog.clear();
        System.setOut(previous);
        System.setProperty("user.dir", userDir);
    }

    List<JsonNode> logs() throws Exception {
        List<JsonNode> out = new ArrayList<>();
        for (String line : bytes.toString(StandardCharsets.UTF_8).split("\\R")) {
            if (line.startsWith("{")) out.add(json.readTree(line));
        }
        return out;
    }

    MockHttpServletResponse run(String id, String data) throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/events");
        request.setServletPath("/events");
        if (id != null) request.addHeader("X-Analysis-Id", id);
        MockHttpServletResponse response = new MockHttpServletResponse();
        new AnalysisLogFilter().doFilter(request, response, (req, res) -> {
            var result = controller.receiveVideoEvent(video, null, data);
            response.setStatus(result.getStatusCode().value());
            response.getWriter().write(result.getBody());
        });
        return response;
    }

    @Test void mapsIdsAndPreservesZeroAndPlainResponse() throws Exception {
        String id = UUID.randomUUID().toString();
        var response = run(id, "{\"droneId\":\"DR-01\",\"vadScore\":0.0,\"maeConfidence\":0.8,\"label\":\"폭력\"}");
        assertEquals(200, response.getStatus());
        assertTrue(response.getContentAsString().contains("ID: 17"));
        List<JsonNode> logs = logs();
        assertTrue(logs.stream().allMatch(log -> id.equals(log.path("analysis_id").asText())));
        JsonNode saved = logs.stream().filter(log -> "db_save".equals(log.path("stage").asText()) && "completed".equals(log.path("event").asText())).findFirst().orElseThrow();
        assertEquals(17, saved.path("event_id").asInt());
        assertEquals(0.0, saved.path("vad_score").asDouble());
        assertEquals("vadScore", saved.path("source_key").asText());
        assertEquals(1, logs.stream().filter(log -> "request_terminal".equals(log.path("stage").asText())).count());
    }

    @Test void dbSuccessPublishFailureIsPartialSuccess() throws Exception {
        doThrow(new RuntimeException("SECRET_SENTINEL")).when(messages).convertAndSend(eq("/topic/events"), any(Map.class));
        assertEquals(500, run(null, "{}").getStatus());
        JsonNode terminal = logs().stream().filter(log -> "request_terminal".equals(log.path("stage").asText())).findFirst().orElseThrow();
        assertEquals("completed", terminal.path("stages").path("db_save").asText());
        assertEquals("failed", terminal.path("stages").path("alert_publish").asText());
        assertEquals(17, terminal.path("event_id").asInt());
        assertFalse(bytes.toString(StandardCharsets.UTF_8).contains("SECRET_SENTINEL"));
    }

    @Test void failedDbPreservesMediaAndDoesNotPublish() throws Exception {
        doThrow(new IllegalStateException("SECRET_SENTINEL")).when(repository).save(any());
        assertEquals(500, run("invalid", "{}").getStatus());
        JsonNode terminal = logs().stream().filter(log -> "request_terminal".equals(log.path("stage").asText())).findFirst().orElseThrow();
        assertEquals("completed", terminal.path("stages").path("backend_video_store").asText());
        assertEquals("failed", terminal.path("stages").path("db_save").asText());
        assertEquals("not_attempted", terminal.path("stages").path("alert_publish").asText());
        verifyNoInteractions(messages);
    }

    @Test void fallbackScoreAndMissingRemainDistinct() throws Exception {
        run(null, "{\"score\":0.25}");
        run(null, "{}");
        var saves = logs().stream().filter(log -> "db_save".equals(log.path("stage").asText()) && "completed".equals(log.path("event").asText())).toList();
        assertEquals("score", saves.get(0).path("source_key").asText());
        assertEquals(.25, saves.get(0).path("vad_score").asDouble());
        assertTrue(saves.get(1).path("vad_score").isNull());
        assertNotEquals(saves.get(0).path("analysis_id"), saves.get(1).path("analysis_id"));
    }

    @Test void invalidJsonDoesNotStoreOrLeak() throws Exception {
        assertEquals(500, run(null, "SECRET_SENTINEL").getStatus());
        verifyNoInteractions(repository, messages);
        assertFalse(bytes.toString(StandardCharsets.UTF_8).contains("SECRET_SENTINEL"));
        AnalysisLog.emit("after", "completed", Map.of());
        assertTrue(logs().stream().noneMatch(log -> "after".equals(log.path("stage").asText())));
    }
}
