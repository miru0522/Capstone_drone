package com.drone.backend.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.Set;
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

/**
 * 실시간 영상 중계 (2026-08-22 드론팀 합의).
 *
 * 드론이 HTTP로 프레임을 올리고(POST), 관제 화면이 MJPEG로 받아간다(GET).
 * <b>STOMP를 쓰지 않는다</b> — 브로커에 영상을 얹으면 EMERGENCY_STOP이
 * 프레임 뒤에 큐잉되고, 프레임 한 장(40~80KB)이 기본 메시지 한계 64KB를 넘는다.
 *
 * 프레임은 메모리에만 있고 저장하지 않는다. 사고 클립은 별도 업로드가 담당한다.
 */
@Slf4j
@Service
public class StreamService {

    /** 시청자가 0명이어도 이만큼은 기다린다 — 명령 전송과 브라우저 접속 사이의 간격 */
    private static final long VIEWER_GRACE_MS = 10_000;
    /** 이 시간 동안 프레임이 없으면 드론이 죽은 것으로 보고 세션을 접는다 */
    private static final long FRAME_STALE_MS = 15_000;
    /** 시청자별 대기열. 느린 화면 때문에 드론이 밀리면 안 되므로 짧게 두고 오래된 것을 버린다 */
    private static final int VIEWER_QUEUE_SIZE = 2;

    public static class Session {
        public final String droneId;
        public final String streamId;
        final long startedAt = System.currentTimeMillis();
        volatile long lastViewerAt = System.currentTimeMillis();
        volatile long lastFrameAt = System.currentTimeMillis();
        final Set<BlockingQueue<byte[]>> viewers = ConcurrentHashMap.newKeySet();

        Session(String droneId, String streamId) {
            this.droneId = droneId;
            this.streamId = streamId;
        }
    }

    // 한 번에 한 대만 중계한다. 드론 대수와 관제 화면 구성상 동시 중계가 필요 없고,
    // 여러 대를 받으면 서버 상행 대역과 메모리가 대수에 비례해 늘어난다.
    private final AtomicReference<Session> current = new AtomicReference<>();

    /**
     * 새 세션을 연다. 이미 다른 드론을 중계 중이었으면 그 드론 ID를 돌려준다 —
     * 호출자가 그쪽에 STOP_STREAM을 보내야 한다.
     */
    public synchronized Session start(String droneId) {
        Session prev = current.get();
        if (prev != null && prev.droneId.equals(droneId)) {
            return prev;   // 이미 같은 드론을 보고 있다. 세션을 갈아엎으면 화면이 끊긴다
        }
        Session s = new Session(droneId, UUID.randomUUID().toString().substring(0, 8));
        current.set(s);
        if (prev != null) closeViewers(prev);
        log.info("📹 {} 스트림 시작 (streamId={})", droneId, s.streamId);
        return s;
    }

    /** 직전에 중계 중이던 다른 드론. 없으면 null */
    public synchronized String previousDroneId(String droneId) {
        Session s = current.get();
        return (s != null && !s.droneId.equals(droneId)) ? s.droneId : null;
    }

    public synchronized void stop(String droneId) {
        Session s = current.get();
        if (s != null && s.droneId.equals(droneId)) {
            current.set(null);
            closeViewers(s);
            log.info("📹 {} 스트림 종료", droneId);
        }
    }

    /** 아직 보고 있는 관제사가 있는가. 마지막 한 명이 나갈 때만 드론을 멈추기 위한 것 */
    public boolean hasViewers(Session s) {
        return s != null && !s.viewers.isEmpty();
    }

    public Session sessionOf(String droneId) {
        Session s = current.get();
        return (s != null && s.droneId.equals(droneId)) ? s : null;
    }

    /**
     * 드론이 올린 프레임을 받는다.
     *
     * @return false면 드론에 410을 돌려준다 — 드론은 즉시 전송을 멈춘다.
     *         STOP_STREAM이 유실되어도 이 경로로 멈출 수 있다.
     */
    public boolean acceptFrame(String droneId, String streamId, byte[] jpeg) {
        Session s = current.get();
        if (s == null || !s.droneId.equals(droneId)) return false;
        // 관제사가 껐다 켜면 옛 세션의 늦은 프레임이 새 세션에 섞인다
        if (streamId != null && !streamId.equals(s.streamId)) return false;

        long now = System.currentTimeMillis();
        s.lastFrameAt = now;

        if (s.viewers.isEmpty()) {
            // 보는 사람이 없다. 다만 명령 직후에는 아직 브라우저가 붙기 전이라 유예를 준다.
            if (now - s.lastViewerAt > VIEWER_GRACE_MS) {
                stop(droneId);
                return false;
            }
        } else {
            s.lastViewerAt = now;
            for (BlockingQueue<byte[]> q : s.viewers) {
                // 가득 차 있으면 가장 오래된 것을 버린다. 실시간이 밀린 프레임보다 중요하다.
                if (!q.offer(jpeg)) { q.poll(); q.offer(jpeg); }
            }
        }
        return true;
    }

    public BlockingQueue<byte[]> addViewer(Session s) {
        BlockingQueue<byte[]> q = new LinkedBlockingQueue<>(VIEWER_QUEUE_SIZE);
        s.viewers.add(q);
        s.lastViewerAt = System.currentTimeMillis();
        return q;
    }

    public void removeViewer(Session s, BlockingQueue<byte[]> q) {
        s.viewers.remove(q);
        s.lastViewerAt = System.currentTimeMillis();   // 마지막 시청자가 나간 시각부터 유예를 센다
    }

    /** 세션이 아직 살아 있는가. 시청자 루프가 매 주기 확인한다 */
    public boolean isAlive(Session s) {
        return current.get() == s
                && System.currentTimeMillis() - s.lastFrameAt < FRAME_STALE_MS;
    }

    private void closeViewers(Session s) {
        // 대기 중인 시청자 루프를 깨운다. isAlive가 false가 되어 스스로 빠져나간다.
        for (BlockingQueue<byte[]> q : s.viewers) q.offer(new byte[0]);
        s.viewers.clear();
    }
}
