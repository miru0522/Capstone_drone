package com.drone.backend.controller;

import com.drone.backend.config.JwtUtil;
import com.drone.backend.service.StreamService;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * 실시간 영상 중계 (2026-08-22 드론팀 합의).
 *
 * <pre>
 * 관제 → 서버 : POST /drones/{id}/stream/start   → 드론에 REQUEST_STREAM
 * 드론 → 서버 : POST /drones/{id}/stream/frame   → 204 계속 / 410 즉시중지
 * 관제 ← 서버 : GET  /drones/{id}/stream         → MJPEG
 * </pre>
 *
 * 드론은 NAT 뒤에 있어 서버가 먼저 붙을 수 없다. 반드시 드론이 발신한다.
 */
@Slf4j
@RestController
@RequestMapping("/drones")
@RequiredArgsConstructor
public class StreamController {

    /** 관제사가 지정하지 않았을 때의 기본값. REQUEST_STREAM에 실어 보내 드론 재빌드 없이 조정한다. */
    private static final int FPS = 5;
    private static final int WIDTH = 640;
    private static final int HEIGHT = 480;
    private static final int QUALITY = 70;

    private static final String BOUNDARY = "frame";
    /** 프레임을 기다리는 최대 시간. 지나면 세션 생존만 확인하고 다시 기다린다. */
    private static final long POLL_SEC = 5;

    private final StreamService streamService;
    private final JwtUtil jwtUtil;
    private final org.springframework.messaging.simp.SimpMessagingTemplate messagingTemplate;

    // ── 관제 → 서버 ────────────────────────────────────────────────

    /**
     * 스트림 요청. VIEWER도 허용한다 — 영상 시청은 조회 업무이고
     * 드론을 움직이는 조작이 아니다.
     */
    @PostMapping("/{droneId}/stream/start")
    public ResponseEntity<?> startStream(@PathVariable String droneId, HttpServletRequest req) {
        if (!isLoggedIn(req)) return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("로그인이 필요합니다.");

        // 한 번에 한 대만 중계한다. 다른 드론을 보고 있었으면 그쪽을 먼저 멈춘다.
        String prev = streamService.previousDroneId(droneId);
        if (prev != null) {
            sendStop(prev);
            log.info("📹 {} 중계를 멈추고 {}로 전환", prev, droneId);
        }

        StreamService.Session s = streamService.start(droneId);

        Map<String, Object> command = new HashMap<>();
        command.put("action", "REQUEST_STREAM");
        command.put("droneId", droneId);
        command.put("streamId", s.streamId);
        command.put("uploadPath", "/drones/" + droneId + "/stream/frame");
        command.put("fps", FPS);
        command.put("width", WIDTH);
        command.put("height", HEIGHT);
        command.put("quality", QUALITY);
        messagingTemplate.convertAndSend("/topic/drones/" + droneId + "/commands", command);

        return ResponseEntity.ok(Map.of("streamId", s.streamId));
    }

    @PostMapping("/{droneId}/stream/stop")
    public ResponseEntity<?> stopStream(@PathVariable String droneId, HttpServletRequest req) {
        if (!isLoggedIn(req)) return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body("로그인이 필요합니다.");

        // 관제사 두 명이 같은 드론을 보고 있을 수 있다. 한 명이 창을 닫았다고
        // 드론을 멈추면 나머지 화면이 함께 죽는다.
        StreamService.Session s = streamService.sessionOf(droneId);
        if (streamService.hasViewers(s)) {
            // 닫는 쪽의 MJPEG 연결은 아직 정리되지 않았을 수 있다. 그래도 안전하다 —
            // 그 연결이 끊기면 시청자가 0명이 되고, 유예 10초 뒤 서버가 410으로 멈춘다.
            return ResponseEntity.ok("다른 관제사가 시청 중이므로 스트림을 유지합니다.");
        }

        sendStop(droneId);
        streamService.stop(droneId);
        return ResponseEntity.ok("스트림을 중지했습니다.");
    }

    // ── 드론 → 서버 ────────────────────────────────────────────────

    /**
     * 프레임 수신. 인증은 DeviceKeyFilter가 X-Device-Key로 처리한다.
     *
     * 응답 자체가 계속·중지 신호다. STOP_STREAM이 유실되어도(관제사가 브라우저를
     * 그냥 닫거나 서버가 재시작되면 그렇게 된다) 드론은 410을 보고 멈출 수 있다.
     */
    @PostMapping("/{droneId}/stream/frame")
    public ResponseEntity<Void> uploadFrame(@PathVariable String droneId,
                                            @RequestHeader(value = "X-Stream-Id", required = false) String streamId,
                                            @RequestBody byte[] jpeg) {
        if (jpeg == null || jpeg.length == 0) return ResponseEntity.noContent().build();
        boolean keepGoing = streamService.acceptFrame(droneId, streamId, jpeg);
        return keepGoing
                ? ResponseEntity.noContent().build()                       // 204 — 계속
                : ResponseEntity.status(HttpStatus.GONE).build();          // 410 — 즉시 중지
    }

    // ── 서버 → 관제 화면 ───────────────────────────────────────────

    /**
     * MJPEG 중계. 브라우저는 {@code <img src="/drones/DR-01/stream">} 한 줄로 받는다.
     * 별도 라이브러리도 코덱도 필요 없다.
     *
     * ⚠️ nginx에 proxy_buffering off가 없으면 프레임이 모였다 뭉텅이로 나와
     *    실시간이 아니게 된다.
     */
    @GetMapping("/{droneId}/stream")
    public ResponseEntity<StreamingResponseBody> viewStream(@PathVariable String droneId, HttpServletRequest req) {
        if (!isLoggedIn(req)) return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();

        StreamService.Session s = streamService.sessionOf(droneId);
        if (s == null) return ResponseEntity.notFound().build();

        StreamingResponseBody body = out -> {
            BlockingQueue<byte[]> q = streamService.addViewer(s);
            try {
                while (streamService.isAlive(s)) {
                    byte[] frame = q.poll(POLL_SEC, TimeUnit.SECONDS);
                    if (frame == null) continue;      // 프레임이 아직 없다. 생존만 다시 확인한다
                    if (frame.length == 0) break;     // 세션 종료 신호
                    writeFrame(out, frame);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (Exception e) {
                // 관제사가 화면을 닫으면 여기서 IOException이 난다. 정상 종료다.
                log.debug("스트림 시청 종료: {}", e.getMessage());
            } finally {
                streamService.removeViewer(s, q);
            }
        };

        return ResponseEntity.ok()
                .header("Content-Type", "multipart/x-mixed-replace; boundary=" + BOUNDARY)
                .header("Cache-Control", "no-store")
                .body(body);
    }

    private void writeFrame(OutputStream out, byte[] jpeg) throws java.io.IOException {
        String header = "--" + BOUNDARY + "\r\n"
                + "Content-Type: image/jpeg\r\n"
                + "Content-Length: " + jpeg.length + "\r\n\r\n";
        out.write(header.getBytes(StandardCharsets.US_ASCII));
        out.write(jpeg);
        out.write("\r\n".getBytes(StandardCharsets.US_ASCII));
        out.flush();   // 즉시 내보내지 않으면 실시간이 아니다
    }

    private void sendStop(String droneId) {
        StreamService.Session s = streamService.sessionOf(droneId);
        Map<String, Object> command = new HashMap<>();
        command.put("action", "STOP_STREAM");
        command.put("droneId", droneId);
        if (s != null) command.put("streamId", s.streamId);
        messagingTemplate.convertAndSend("/topic/drones/" + droneId + "/commands", command);
    }

    private boolean isLoggedIn(HttpServletRequest req) {
        String token = jwtUtil.extractTokenFromRequest(req);
        return token != null && jwtUtil.validateToken(token);
    }
}
