"""Structured Japanese ASR result types with no model dependency."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DecodeResult:
    """One recognizer result before and after deterministic display cleanup.

    ``token_log_probs`` preserves sherpa-onnx's ``ys_log_probs`` values, when
    present.  They are deliberately not called confidence: their semantics
    and calibration are model-specific and have not been established.
    """

    raw_text: str
    text: str
    lang: str = ""
    tier: str = ""
    tokens: tuple[str, ...] = ()
    timestamps: tuple[float, ...] = ()
    token_log_probs: tuple[float, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityAssessment:
    risk_score: float
    risk_reasons: tuple[str, ...]
    risk_signals: dict[str, float | bool | str | None]

    def as_dict(self) -> dict[str, object]:
        return {
            "risk_score": self.risk_score,
            "risk_reasons": list(self.risk_reasons),
            "risk_signals": dict(self.risk_signals),
        }
