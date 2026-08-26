package com.drone.backend.controller;

import com.drone.backend.domain.EventLog;
import com.drone.backend.repository.EventLogRepository;
import com.drone.backend.service.TtsService;
import com.drone.backend.repository.DroneRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import org.springframework.web.multipart.MultipartFile;
import org.springframework.http.MediaType;
import java.io.File;
import java.util.HashMap;
import java.util.Map;
import java.util.List;
import java.util.stream.Collectors;
import com.drone.backend.dto.EventLogDto;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.type.TypeReference;

@RestController
@RequestMapping("/events")
@RequiredArgsConstructor
@Slf4j
public class EventController {

    private final EventLogRepository eventLogRepository;
    private final DroneRepository droneRepository;
    private final TtsService ttsService;
    private final org.springframework.messaging.simp.SimpMessagingTemplate messagingTemplate;

    @GetMapping
    public ResponseEntity<List<EventLogDto>> getAllEvents() {
        log.info("📊 [REST] 전체 이벤트 로그 조회");
        List<EventLogDto> events = eventLogRepository.findAll()
                .stream()
                .map(EventLogDto::fromEntity)
                .collect(Collectors.toList());
        return ResponseEntity.ok(events);
    }

    @PostMapping("/{eventId}/tts-approval")
    public ResponseEntity<String> approveTts(@PathVariable Long eventId) {
        log.info("👨‍💻 [REST] 관리자가 이벤트(ID: {})의 TTS 경고 송출을 승인했습니다.", eventId);

        EventLog eventLog = eventLogRepository.findById(eventId)
                .orElseThrow(() -> new IllegalArgumentException("이벤트를 찾을 수 없습니다."));

        // 관제사가 둘 이상 접속해 같은 경보를 승인하면 현장에 경고 방송이 두 번 나간다.
        // 한 번 승인된 건은 조용히 돌려보낸다 — 실패가 아니므로 200으로 답한다.
        String status = eventLog.getAdminApprovalStatus();
        if ("APPROVED".equals(status) || "BROADCAST_COMPLETED".equals(status)) {
            log.info("👨‍💻 [REST] 이벤트(ID: {})는 이미 승인됨({}). 중복 송출을 막는다.", eventId, status);
            return ResponseEntity.ok("이미 승인된 이벤트입니다.");
        }

        // 상태 업데이트
        eventLog.setAdminApprovalStatus("APPROVED");
        eventLogRepository.save(eventLog);

        // TTS 비동기 생성 및 드론 전송 시작
        ttsService.generateAndSendTts(eventId);

        return ResponseEntity.ok("승인 완료. TTS가 생성되어 드론으로 전송됩니다.");
    }

    @PostMapping("/{eventId}/broadcast-complete")
    public ResponseEntity<String> broadcastCompleteCallback(@PathVariable Long eventId) {
        log.info("📢 [REST Callback] 드론 현장 오디오 송출 완료 수신 (이벤트 ID: {})", eventId);

        EventLog eventLog = eventLogRepository.findById(eventId)
                .orElseThrow(() -> new IllegalArgumentException("이벤트를 찾을 수 없습니다."));

        // 상태 업데이트
        eventLog.setAdminApprovalStatus("BROADCAST_COMPLETED");
        eventLogRepository.save(eventLog);

        // 웹소켓을 통한 대시보드 상태 갱신 알림
        messagingTemplate.convertAndSend("/topic/events/status", 
            "{\"eventId\": " + eventId + ", \"status\": \"COMPLETED\"}");

        return ResponseEntity.ok("송출 완료 상태가 성공적으로 업데이트되었습니다.");
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<String> receiveVideoEvent(
            @RequestPart("video") MultipartFile video,
            @RequestPart(value = "audio", required = false) MultipartFile audio,
            @RequestPart("eventData") String eventDataStr) {
        log.info("📹 [REST] FastAPI로부터 비디오 및 이벤트 데이터 수신 시작");
        try {
            // 1. JSON 파싱
            ObjectMapper mapper = new ObjectMapper();
            Map<String, Object> eventData = mapper.readValue(eventDataStr, new TypeReference<Map<String, Object>>() {});

            // 2. 비디오 저장 경로 설정 (WebConfig 매핑 기준인 프로젝트 루트의 videodata/)
            String originalFilename = video.getOriginalFilename();
            if (originalFilename == null || originalFilename.isEmpty()) {
                originalFilename = System.currentTimeMillis() + "_video.mp4";
            }
            
            String uploadDir = System.getProperty("user.dir") + "/videodata/";
            File dir = new File(uploadDir);
            if (!dir.exists()) {
                dir.mkdirs();
            }
            File dest = new File(uploadDir + originalFilename);
            video.transferTo(dest);
            
            // 상대 경로 생성
            String videoUrl = "/media/" + originalFilename;

            // 3. DB 저장 (이상 점수 스키마 분리 적용)
            EventLog logEvent = new EventLog();
            
            Object vadObj = eventData.get("vadScore");
            if (vadObj != null) {
                logEvent.setFirstAnomalyScore(Double.parseDouble(vadObj.toString()));
            } else {
                logEvent.setFirstAnomalyScore(Double.parseDouble(eventData.getOrDefault("score", "0").toString()));
            }

            Object maeObj = eventData.get("maeConfidence");
            if (maeObj != null) {
                logEvent.setSecondAnomalyScore(Double.parseDouble(maeObj.toString()));
            }
            
            Object descObj = eventData.get("description");
            logEvent.setVlmSituationDesc(descObj != null ? descObj.toString() : null);
            
            Object ttsObj = eventData.get("ttsText");
            logEvent.setVlmTtsCandidate(ttsObj != null ? ttsObj.toString() : null);
            
            Object labelObj = eventData.getOrDefault("label", eventData.get("type"));
            logEvent.setSecondClassificationResult(labelObj != null ? labelObj.toString() : null);
            
            logEvent.setVideoClipPath(videoUrl);
            
            // [추가] 사용자가 curl 등으로 요청 시 특정 드론을 명시했다면 해당 드론 연결
            if (eventData.containsKey("droneId") && eventData.get("droneId") != null) {
                String requestedDroneId = eventData.get("droneId").toString();
                // 등록된 드론일 때만 기록한다 — 임의의 문자열이 들어와 기록을 오염시키지 않도록.
                // logEvent는 아래에서 save() 결과로 재할당되므로 람다로 캡처할 수 없다.
                if (droneRepository.existsByDroneId(requestedDroneId)) {
                    logEvent.setDroneId(requestedDroneId);
                }
            }

            // 2.5 오디오(TTS) 저장 경로 설정
            if (audio != null && !audio.isEmpty()) {
                String audioFilename = audio.getOriginalFilename();
                if (audioFilename == null || audioFilename.isEmpty()) {
                    audioFilename = System.currentTimeMillis() + "_audio.wav";
                }
                String audioUploadDir = System.getProperty("user.dir") + "/wavdata/";
                File audioDir = new File(audioUploadDir);
                if (!audioDir.exists()) {
                    audioDir.mkdirs();
                }
                File audioDest = new File(audioUploadDir + audioFilename);
                audio.transferTo(audioDest);
                
                logEvent.setAudioFilePath("/wavdata/" + audioFilename);
            }

            logEvent = eventLogRepository.save(logEvent);

            log.info("✅ [REST] 이벤트 DB 저장 완료. ID: {}", logEvent.getEventId());

            // 4. STOMP 대시보드 알림 브로드캐스트
            Map<String, Object> alertData = new HashMap<>();
            alertData.put("id", logEvent.getEventId());
            alertData.put("type", eventData.get("type"));
            alertData.put("label", eventData.get("label"));
            
            Object displayLabelObj = eventData.containsKey("label") ? eventData.get("label") : eventData.get("type");
            String displayLabel = displayLabelObj != null ? displayLabelObj.toString() : "Unknown";
            
            alertData.put("title", "VLM Alarm: " + displayLabel);
            alertData.put("desc", eventData.get("description"));
            alertData.put("ttsText", eventData.get("ttsText"));
            alertData.put("videoUrl", videoUrl);
            alertData.put("time", java.time.LocalTime.now().toString());

            messagingTemplate.convertAndSend("/topic/events", alertData);
            log.info("🚀 [STOMP] 대시보드로 알림 송출 완료");

            return ResponseEntity.ok("이벤트 접수 및 브로드캐스트 성공. (ID: " + logEvent.getEventId() + ")");
            
        } catch (Exception e) {
            log.error("❌ 비디오 이벤트 수신 실패", e);
            return ResponseEntity.status(500).body("Error: " + e.getMessage());
        }
    }
}
