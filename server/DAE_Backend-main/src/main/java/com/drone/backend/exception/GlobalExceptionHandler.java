package com.drone.backend.exception;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestControllerAdvice
public class GlobalExceptionHandler {

    // ⚠️ Map.of()는 값이 null이면 NPE를 던진다. e.getMessage()는 null일 수 있으므로
    //    반드시 이 헬퍼를 거쳐 응답을 만든다. (핸들러 안에서 터지면 원인 추적이 어려워진다)
    private ResponseEntity<?> body(HttpStatus status, String error, String message) {
        return ResponseEntity.status(status).body(Map.of(
                "status", status.value(),
                "error", error,
                "message", message == null ? "" : message
        ));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<?> handleIllegalArgument(IllegalArgumentException e) {
        return body(HttpStatus.BAD_REQUEST, "Bad Request", e.getMessage());
    }

    @ExceptionHandler(NullPointerException.class)
    public ResponseEntity<?> handleNullPointer(NullPointerException e) {
        return body(HttpStatus.BAD_REQUEST, "Null Pointer", e.getMessage());
    }

    /**
     * 요청 본문의 형태가 컨트롤러 시그니처와 맞지 않을 때(예: [lat,lng] 배열을 {lat,lng} 자리에 전송).
     * 클라이언트 잘못이므로 500이 아니라 400으로 돌려준다. 이게 없으면 아래 Exception 핸들러가
     * 전부 500으로 뭉개서 원인 파악이 어려워진다.
     */
    @ExceptionHandler(org.springframework.http.converter.HttpMessageNotReadableException.class)
    public ResponseEntity<?> handleUnreadableBody(
            org.springframework.http.converter.HttpMessageNotReadableException e) {
        return body(HttpStatus.BAD_REQUEST, "Malformed Request Body",
                "요청 본문의 형식이 올바르지 않습니다. " + e.getMostSpecificCause().getMessage());
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<?> handleGeneralException(Exception e) {
        return body(HttpStatus.INTERNAL_SERVER_ERROR, "Internal Server Error", e.getMessage());
    }
}