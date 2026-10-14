"""Insight 중요도: baseImportance + signalStrength → finalImportance(0~100)."""
from typing import Protocol


class InsightImportanceStrategy(Protocol):
    version: str

    def linear(
        self, signal: float, signal_lo: float, signal_hi: float, base: int, max_imp: int, min_imp: int = 0
    ) -> int: ...


class LinearImportanceStrategy:
    """signal_lo에서 base, signal_hi 이상에서 max_imp. 그 사이 선형."""

    version = "importance_linear_v1"

    def linear(
        self, signal: float, signal_lo: float, signal_hi: float, base: int, max_imp: int, min_imp: int = 0
    ) -> int:
        if signal_hi == signal_lo:
            ratio = 1.0 if signal >= signal_hi else 0.0
        else:
            ratio = (signal - signal_lo) / (signal_hi - signal_lo)
        ratio = max(0.0, min(1.0, ratio))
        value = base + (max_imp - base) * ratio
        return int(round(max(min_imp, min(max_imp, value))))


importance_strategy: InsightImportanceStrategy = LinearImportanceStrategy()
