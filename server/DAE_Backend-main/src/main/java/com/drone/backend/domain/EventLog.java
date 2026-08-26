package com.drone.backend.domain;

import jakarta.persistence.*;
import lombok.*;

import com.fasterxml.jackson.annotation.JsonIgnore;
import java.time.LocalDateTime;

@Entity
@Table(name = "event_logs")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class EventLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long eventId;

    @Column(nullable = false)
    private LocalDateTime timestamp;

    // drones PK를 가리키던 FK를 업무키 문자열로 바꿨다.
    // 드론이 삭제·퇴역해도 이벤트 기록은 어느 드론이 감지했는지 계속 말할 수 있어야 한다.
    @Column(name = "drone_id", length = 50)
    private String droneId;

    @Column(name = "first_anomaly_score")
    private Double firstAnomalyScore; // 1차 필터링(VAD) 점수

    @Column(name = "second_anomaly_score")
    private Double secondAnomalyScore; // 2차 서버 연산(VideoMAE) 점수

    @Column(name = "second_classification_result", length = 50)
    private String secondClassificationResult; // 2차 서버 연산 결과 (예: 폭행, 화재 등)

    @Column(name = "vlm_situation_desc", length = 1000)
    private String vlmSituationDesc; // VLM이 생성한 상황 설명 텍스트

    @Column(name = "vlm_tts_candidate", length = 500)
    private String vlmTtsCandidate; // VLM이 생성한 TTS 경고 문구 후보

    @Column(name = "admin_approval_status", length = 20)
    private String adminApprovalStatus; // 대기(PENDING) / 승인(APPROVED) / 반려(REJECTED)

    @Column(name = "human_dispatch_flag")
    private Boolean humanDispatchFlag; // 오프라인 인력 출동 여부

    @Column(name = "audio_file_path", length = 255)
    private String audioFilePath; // 생성된 TTS 오디오 파일 경로

    @Column(name = "video_clip_path", length = 255)
    private String videoClipPath; // 이상 행동 원본 영상 경로 (S3 또는 로컬 경로)

    @PrePersist
    protected void onCreate() {
        this.timestamp = LocalDateTime.now();
        if (this.adminApprovalStatus == null) {
            this.adminApprovalStatus = "PENDING"; // 기본값 대기
        }
        if (this.humanDispatchFlag == null) {
            this.humanDispatchFlag = false; // 기본값 미출동
        }
    }
}
