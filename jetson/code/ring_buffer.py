"""
ring_buffer.py
CSI 카메라에서 들어오는 프레임을 메모리 내 deque로 순환 저장하는 링 버퍼.

설계 파라미터:
    - FPS: 9
    - 버퍼 길이: 9초 (81 프레임)
    - 추론 창: 1초 (9 프레임, 슬라이딩 윈도우) — WideBranchNet 입력 요구사항
      (★2026-08-26: docstring이 실제 INFER_WINDOW_SECONDS=1과 어긋나 있던
      것을 수정. main.py detect_anomaly()의 T=9(1초) 설명과 일치시킴)
"""

import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List

import numpy as np


# ─── 설정값 ──────────────────────────────────────────────────────
FPS = 9
BUFFER_SECONDS = 9
INFER_WINDOW_SECONDS = 1  # WideBranchNet 모델 요구사항: 9프레임(1초) 단위

BUFFER_MAXLEN = FPS * BUFFER_SECONDS          # 81 프레임
INFER_WINDOW_LEN = FPS * INFER_WINDOW_SECONDS  # 45 프레임


@dataclass
class FrameEntry:
    """타임스탬프가 포함된 단일 프레임."""
    frame: np.ndarray
    timestamp: float = field(default_factory=time.time)


class RingBuffer:
    """
    스레드 안전한 고정 길이 프레임 링 버퍼.

    - push(frame): 카메라 캡처 루프에서 매 프레임 호출
    - get_latest_window(n): 최근 n개 프레임 슬라이딩 윈도우 (추론용)
    - get_full_buffer(): 버퍼 전체 스냅샷 (트리거 시 전송용)
    """

    def __init__(self, maxlen: int = BUFFER_MAXLEN):
        self.maxlen = maxlen
        self._buffer: deque[FrameEntry] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray) -> None:
        """새 프레임을 버퍼에 추가. 가득 차면 가장 오래된 프레임이 자동 제거됨."""
        with self._lock:
            self._buffer.append(FrameEntry(frame=frame))

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)

    def is_ready_for_inference(self, window_len: int = INFER_WINDOW_LEN) -> bool:
        """추론 창을 채울 만큼 프레임이 쌓였는지 확인."""
        with self._lock:
            return len(self._buffer) >= window_len

    def get_latest_window(self, window_len: int = INFER_WINDOW_LEN) -> Optional[np.ndarray]:
        """
        최근 window_len개 프레임을 (T, H, W, C) numpy 배열로 반환.
        추론 모델 입력용 슬라이딩 윈도우. 프레임이 부족하면 None.
        """
        with self._lock:
            if len(self._buffer) < window_len:
                return None
            recent = list(self._buffer)[-window_len:]
        return np.stack([e.frame for e in recent], axis=0)

    def get_full_buffer(self) -> List[FrameEntry]:
        """
        버퍼 전체 스냅샷 반환 (트리거 발생 시 전송용).
        스냅샷이므로 호출 이후 버퍼가 계속 갱신되어도 영향받지 않음.
        """
        with self._lock:
            return list(self._buffer)

    def get_fill_ratio(self) -> float:
        """버퍼가 얼마나 채워졌는지 (0.0~1.0). 디버깅/모니터링용."""
        with self._lock:
            return len(self._buffer) / self.maxlen
