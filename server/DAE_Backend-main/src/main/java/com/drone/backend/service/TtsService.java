package com.drone.backend.service;

import com.drone.backend.domain.EventLog;
import com.drone.backend.repository.EventLogRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

@Service
@RequiredArgsConstructor
@Slf4j
public class TtsService {

    private final EventLogRepository eventLogRepository;
    private final org.springframework.messaging.simp.SimpMessagingTemplate messagingTemplate;

    @org.springframework.beans.factory.annotation.Value("${app.ai-server.base-url:http://ai_server:8000}")
    private String aiBaseUrl;


    /**
     * 관리자 승인 시 호출되는 TTS 오디오 생성 및 드론/테스트 드라이버 전송 파이프라인
     */
    public void generateAndSendTts(Long eventId) {
        CompletableFuture.runAsync(() -> {
            try {
                EventLog eventLog = eventLogRepository.findById(eventId)
                        .orElseThrow(() -> new IllegalArgumentException("이벤트를 찾을 수 없습니다."));

                String textToSpeech = eventLog.getVlmTtsCandidate() != null ? eventLog.getVlmTtsCandidate() : "경고합니다. 즉시 대피하십시오.";
                log.info("🎙️ [REST] FastAPI 서버로 TTS 오디오 요청 중... (승인된 텍스트: {})", textToSpeech);

                // FastAPI 서버로 REST 요청 (RestTemplate)
                org.springframework.web.client.RestTemplate restTemplate = new org.springframework.web.client.RestTemplate();
                String fastApiUrl = aiBaseUrl + "/tts";

                // 요청 Body 구성
                java.util.Map<String, String> requestBody = new java.util.HashMap<>();
                requestBody.put("text", textToSpeech);
                
                // FastAPI는 application/json 형식을 기대하므로 헤더 명시
                org.springframework.http.HttpHeaders headers = new org.springframework.http.HttpHeaders();
                headers.setContentType(org.springframework.http.MediaType.APPLICATION_JSON);
                org.springframework.http.HttpEntity<java.util.Map<String, String>> requestEntity = new org.springframework.http.HttpEntity<>(requestBody, headers);
                
                // WAV 파일 바이트 배열로 수신
                byte[] audioBytes = restTemplate.postForObject(fastApiUrl, requestEntity, byte[].class);
                
                if (audioBytes == null || audioBytes.length == 0) {
                    log.error("❌ FastAPI에서 빈 오디오 데이터를 반환했습니다.");
                    return;
                }

                // 오디오 파일을 프론트가 접근할 수 있는 ./wavdata/ 폴더에 저장
                String fileName = "tts_" + UUID.randomUUID() + ".wav";
                Path wavDataDir = Paths.get("./wavdata");
                if (!Files.exists(wavDataDir)) {
                    Files.createDirectories(wavDataDir);
                }
                Path targetPath = wavDataDir.resolve(fileName);
                Files.write(targetPath, audioBytes);
                log.info("✅ [REST] FastAPI TTS 다운로드 및 저장 성공: {}", targetPath.toAbsolutePath());

                // 파일 경로 DB 저장 (절대경로 대신 웹 매핑 상대경로 저장)
                String relativeAudioPath = "/wavdata/" + fileName;
                eventLog.setAudioFilePath(relativeAudioPath);
                eventLogRepository.save(eventLog);

                // 3. 공식 스펙(drone_communication_spec.md)에 따른 STOMP 제어 명령 발송
                // [수정 2026-08-05] "DR-test" 폴백 제거.
                // 존재하지 않는 드론 ID로 방송 명령을 쏘면 아무도 수신하지 못한 채
                // 로그에는 "발송 완료"만 남아 장애가 은폐된다.
                // 대상을 특정할 수 없으면 발송하지 않고 경고만 남긴다.
                //
                // [수정 2026-08-17] EventLog가 드론을 FK가 아닌 업무키 문자열로 들게 되면서
                // 지연로딩 프록시가 사라졌다. 비동기 스레드에서의
                // LazyInitializationException 우회(재조회)도 함께 불필요해졌다.
                String targetDroneId = eventLog.getDroneId();

                if (targetDroneId == null) {
                    log.warn("⚠️ 이벤트(id={})에 연결된 드론을 특정할 수 없어 PLAY_AUDIO 발송을 생략합니다. "
                            + "TTS 파일은 생성·저장되었습니다: {}", eventId, targetPath.getFileName());
                    return;
                }

                java.util.Map<String, Object> command = new java.util.HashMap<>();
                command.put("action", "PLAY_AUDIO");
                command.put("droneId", targetDroneId);
                // 드론이 방송을 마치고 POST /events/{eventId}/broadcast-complete 를 부르려면
                // 어느 이벤트였는지 알아야 한다. 이 값이 없어 콜백을 호출할 수 없었다.
                command.put("eventId", eventId);
                command.put("audioBase64", java.util.Base64.getEncoder().encodeToString(audioBytes));
                messagingTemplate.convertAndSend("/topic/drones/" + targetDroneId + "/commands", command);
                log.info("🔊 [STOMP] 드론 채널(/topic/drones/{}/commands)로 PLAY_AUDIO 명령(Base64) 발송 완료!", targetDroneId);

            } catch (Exception e) {
                log.error("TTS 처리 및 전송 중 오류 발생", e);
            }
        });
    }
}
