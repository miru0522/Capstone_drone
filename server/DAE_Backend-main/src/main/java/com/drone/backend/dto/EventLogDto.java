package com.drone.backend.dto;

import com.drone.backend.domain.EventLog;
import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@Builder
public class EventLogDto {
    private Long eventId;
    private LocalDateTime timestamp;
    private String droneId;
    private Double firstAnomalyScore;
    private Double secondAnomalyScore;
    private String secondClassificationResult;
    private String vlmSituationDesc;
    private String vlmTtsCandidate;
    private String adminApprovalStatus;
    private Boolean humanDispatchFlag;
    private String audioFilePath;
    private String videoClipPath;

    public static EventLogDto fromEntity(EventLog eventLog) {
        return EventLogDto.builder()
                .eventId(eventLog.getEventId())
                .timestamp(eventLog.getTimestamp())
                .droneId(eventLog.getDroneId())
                .firstAnomalyScore(eventLog.getFirstAnomalyScore())
                .secondAnomalyScore(eventLog.getSecondAnomalyScore())
                .secondClassificationResult(eventLog.getSecondClassificationResult())
                .vlmSituationDesc(eventLog.getVlmSituationDesc())
                .vlmTtsCandidate(eventLog.getVlmTtsCandidate())
                .adminApprovalStatus(eventLog.getAdminApprovalStatus())
                .humanDispatchFlag(eventLog.getHumanDispatchFlag())
                .audioFilePath(eventLog.getAudioFilePath())
                .videoClipPath(eventLog.getVideoClipPath())
                .build();
    }
}
