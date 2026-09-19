"""MAVSDK 배터리 잔량 단위를 한 프로세스 안에서 일관되게 정규화한다."""

import math
import os
from typing import Optional


class BatteryPercentNormalizer:
    """fraction(0~1)과 percent(0~100) 입력을 설정 또는 관측으로 구분한다."""

    def __init__(self, unit: Optional[str] = None):
        configured = (unit or os.environ.get("BATTERY_REMAINING_UNIT", "auto")).lower()
        if configured not in ("auto", "fraction", "percent"):
            raise ValueError(
                "BATTERY_REMAINING_UNIT must be auto, fraction, or percent"
            )
        self.configured_unit = configured
        self.detected_unit = None if configured == "auto" else configured

    def normalize(self, raw_value: float) -> float:
        raw = float(raw_value)
        if not math.isfinite(raw) or raw < 0.0:
            raise ValueError(f"invalid battery remaining_percent: {raw}")

        if self.detected_unit is None and raw > 1.0:
            self.detected_unit = "percent"

        unit = self.detected_unit or "fraction"
        percent = raw * 100.0 if unit == "fraction" else raw
        if percent > 100.0:
            raise ValueError(
                f"battery percent out of range after {unit} conversion: {percent}"
            )
        return percent

    @property
    def unit(self) -> str:
        return self.detected_unit or "fraction-pending-auto-detection"
