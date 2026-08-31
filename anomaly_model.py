"""
anomaly_model.py
VadCLIP 기반 Edge 1차 이상탐지 파이프라인.

main.py와의 외부 인터페이스는 기존과 동일하게 유지한다.
    AnomalyPipeline()
    AnomalyPipeline.compute_score(window) -> float (0.0~1.0)

기존 YOLOv5n + WideBranchNet(Jigsaw-VAD) TensorRT 경로는 더 이상 로드하지 않는다.
롤백은 Git의 기존 anomaly_model.py로 복원하면 된다.
"""

import logging
import time

import numpy as np

from vadclip_adapter import VadCLIPScorer

logger = logging.getLogger("anomaly_model")


class AnomalyPipeline:
    """
    main.py의 detect_anomaly(window)에서 사용하는 VadCLIP 파이프라인.

    window:
        (T, H, W, C) uint8 BGR.
        T는 ring_buffer.INFER_WINDOW_LEN(기본 48프레임 @ 9fps).

    반환:
        VadCLIP C-branch 최신 10 snippet의 top-k 평균 점수.
        0.0~1.0, 높을수록 이상.
    """

    def __init__(self):
        logger.info("VadCLIP 초기화 시작")
        self.scorer = VadCLIPScorer()
        logger.info("✅ AnomalyPipeline(VadCLIP) 초기화 완료")

    def warmup(self) -> float:
        """Run one synthetic inference before live capture and reset history."""
        logger.info("VadCLIP warmup 시작")
        t0 = time.perf_counter()
        score = self.scorer.warmup()
        logger.info("VadCLIP warmup 완료: %.1fms", (time.perf_counter() - t0) * 1000.0)
        return score

    def compute_score(self, window: np.ndarray) -> float:
        t0 = time.perf_counter()
        score = self.scorer.compute_score(window)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "[진단] VadCLIP 추론 total=%.1fms, feature_buffer=%d/%d, score=%.6f",
            elapsed_ms,
            self.scorer.feature_buffer_len,
            self.scorer.visual_length,
            score,
        )
        return score
