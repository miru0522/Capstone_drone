package com.drone.backend.event;

import com.drone.backend.domain.CommandLog;
import com.drone.backend.repository.CommandLogRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;

/**
 * 조작 이력을 남긴다.
 *
 * 브로드캐스터와 <b>일부러 나눠 뒀다.</b> 하나가 실패해도 다른 쪽은 돌아야 한다 —
 * DB가 잠깐 막혀도 관제사들끼리는 서로의 조작을 봐야 하고, 반대로 STOMP 가
 * 끊겨도 이력은 남아야 한다.
 *
 * 저장에 실패해도 명령 자체는 이미 드론에 나갔다. 예외를 밖으로 던지지 않는다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class CommandLogRecorder {

    private final CommandLogRepository repository;

    @EventListener
    public void onDroneCommand(DroneCommandEvent event) {
        // 사람이 누른 것만 남긴다. 서버가 스스로 보낸 재동기화 명령은 조작 이력이 아니다.
        if (event.getOperator() == null) return;

        try {
            repository.save(CommandLog.builder()
                    .droneId(event.getDroneId())
                    .action(String.valueOf(event.getCommand().get("action")))
                    .operator(event.getOperator())
                    .timestamp(LocalDateTime.now())
                    .build());
        } catch (Exception e) {
            log.warn("조작 이력 저장 실패 (명령은 이미 전송됨) drone={} action={}: {}",
                    event.getDroneId(), event.getCommand().get("action"), e.getMessage());
        }
    }
}
