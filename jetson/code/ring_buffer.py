"""
ring_buffer.py
CSI 카메라에서 들어오는 프레임을 메모리 내 deque로 순환 저장하는 링 버퍼.

설계 파라미터:
    - 카메라 FPS: 9
    - 전송 버퍼: 9초 (81 프레임)
    - VadCLIP 추론 창: 약 5.33초 (48 프레임 @ 9fps)

VadCLIP UCF-Crime feature 규약은 30fps 기준 16-frame stride이고,
한 번의 Edge 판정에서 10 snippet을 추가한다. 라이브 카메라는 9fps이므로
동일한 시간 간격(16/30초)을 보존하도록 약 48프레임을 한 판정 창으로 사용한다.
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

# VadCLIP의 학습/공식 feature 시간축 규약
VADCLIP_REFERENCE_FPS = 30.0
VADCLIP_STRIDE = 16
VADCLIP_SNIPPETS_PER_WINDOW = 10

BUFFER_MAXLEN = FPS * BUFFER_SECONDS  # 81 프레임
INFER_WINDOW_SECONDS = (
    VADCLIP_STRIDE * VADCLIP_SNIPPETS_PER_WINDOW / VADCLIP_REFERENCE_FPS
)  # 5.333...초
INFER_WINDOW_LEN = round(FPS * INFER_WINDOW_SECONDS)  # 48 프레임 @ 9fps


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
