package com.drone.backend.domain;

import jakarta.persistence.*;
import lombok.*;

// DB테이블 설계에 맞게 수정 필요

@Entity
@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * 로그인 아이디. 길이 제한은 화면·서버·컬럼 세 곳이 같은 값을 봐야 한다
     * (USER_ID_MAX). 어긋나면 화면을 통과한 값이 DB에서 터진다.
     */
    @Column(name = "user_Id", nullable = false, length = 32)
    private String userId;

    @Column(name = "pwd", nullable = false, length = 512)
    private String pwd;

    @Column(name = "email", nullable = false, length = 100)
    private String email;

    @Column(name = "name", nullable = false, length = 20)
    private String name;

    /**
     * 프로필 사진의 상대 URL (예: /profile/3f2a....png).
     * null이면 프론트가 "하늘색 배경 + 아이디" 기본 아바타를 그린다.
     * 파일을 따로 만들어 두지 않으므로 아이디가 바뀌어도 기본 아바타가 자동으로 따라간다.
     */
    @Column(name = "profile_image", length = 255)
    private String profileImage;

    @Enumerated(EnumType.STRING)
    @Column(name = "role", nullable = false, length = 20)
    private Role role;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private Status status;

    @Column(name = "created_at")
    private java.time.LocalDateTime createdAt;

    @Column(name = "approved_at")
    private java.time.LocalDateTime approvedAt;

    @Column(name = "approved_by")
    private Long approvedBy;

    /**
     * 로그인이 막힌 이유. 본인이 로그인을 시도하면 이 문구를 보여준다.
     *
     * <b>반려(REJECTED)와 보관(DISABLED)이 이 컬럼을 함께 쓴다.</b> 둘 다
     * "로그인이 막힌 이유"라는 성격이 같고, 승인·복원 시 지워지는 것도 같다.
     * 컬럼 이름이 reject_reason 인 것은 반려에만 쓰던 시절의 잔재다 - 표기
     * 하나 때문에 컬럼을 갈아엎지 않는다. 화면 라벨은 상태에 따라 갈린다.
     *
     * 선택 입력이므로 비어 있을 수 있다 - 그때는 사유 없이 사실만 알린다.
     */
    @Column(name = "reject_reason", length = 500)
    private String rejectReason;

    @PrePersist
    protected void onCreate() {
        this.createdAt = java.time.LocalDateTime.now();
        // 최소 권한으로 시작한다. 승인은 "가입 허가"일 뿐이고,
        // 드론 조작 권한은 관리자가 VIEWER → OPERATOR로 올려 주는 별도 행위다.
        // (예전 기본값은 OPERATOR라, 승인하는 순간 바로 기체를 움직일 수 있었다)
        if (this.role == null) {
            this.role = Role.VIEWER;
        }
        if (this.status == null) {
            this.status = Status.PENDING;
        }
    }
}
