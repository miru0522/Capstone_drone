package com.drone.backend.dto;

/**
 * 드론 → 백엔드 텔레메트리.
 *
 * ⚠️ <b>이 레코드는 프론트로 나가는 페이로드이기도 하다.</b>
 * {@code TelemetryController}가 드론의 JSON을 이 타입으로 역직렬화한 뒤
 * <b>다시 직렬화해서</b> {@code /topic/telemetry}로 브로드캐스트하기 때문에,
 * 여기에 없는 필드는 드론이 보내도 <b>조용히 사라진다.</b>
 * 텔레메트리에 필드를 추가할 때는 드론·프론트뿐 아니라 반드시 이 레코드도 같이 고칠 것.
 */
public record Telemetry(
        double ts,
        String msg_type,
        /**
         * 드론을 가리키는 값. MAVLink {@code sysid}(1~255 정수)와는 다르다 —
         * 이 값은 서버에 등록된 드론의 업무키("DR-01")이므로 이름을 구분해 쓴다.
         */
        String droneId,
        String status,
        /** 지금 수행 중인 명령. 없으면 null (드론이 자율 판단으로 움직이는 중) */
        String currentAction,
        /** 재개할 웨이포인트가 남아 있는가. PAUSED일 때 "순찰 재개"/"순찰 시작"을 가른다 */
        Boolean hasRoute,
        GPS gps,
        Battery battery,
        java.util.Map<String, Object> station
) {
    /** 구버전 드론(추가 필드 미전송) 호환용 */
    public Telemetry(double ts, String msg_type, String droneId, String status, GPS gps, Battery battery) {
        this(ts, msg_type, droneId, status, null, null, gps, battery, null);
    }
}
