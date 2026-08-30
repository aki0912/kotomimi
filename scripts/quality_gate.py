"""Explainable, model-free risk signals for Japanese ASR output."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import re
import unicodedata

from japanese_types import QualityAssessment


_DEFAULT_WEIGHTS = {
    "empty_output": 1.0,
    "very_low_chars_per_second": 0.35,
    "very_high_chars_per_second": 0.35,
    "excessive_repetition": 0.5,
    "unexpected_latin_ratio": 0.45,
    "boundary_forced_split": 0.2,
    "short_boundary_overlap": 0.25,
    "digit_loss": 0.45,
    "primary_refine_disagreement": 0.4,
    "secondary_disagreement": 0.3,
    "suspicious_single_character": 0.3,
    "unresolved_lexicon_candidate": 0.2,
    "low_token_log_probability": 0.35,
}


@dataclass(frozen=True)
class QualityGateSettings:
    high_risk_threshold: float = 0.35
    min_chars_per_second: float = 3.1
    max_chars_per_second: float = 12.0
    min_density_audio_s: float = 1.0
    unexpected_latin_ratio: float = 0.8
    min_unexpected_latin_chars: int = 8
    min_boundary_overlap_s: float = 0.2
    disagreement_threshold: float = 0.35
    min_mean_token_log_probability: float = -0.22
    weights: dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_WEIGHTS))


@dataclass(frozen=True)
class QualityContext:
    text: str
    audio_s: float
    lang: str = "ja"
    raw_text: str | None = None
    forced_split: bool = False
    boundary_overlap_s: float = 0.0
    refined_text: str | None = None
    secondary_text: str | None = None
    unresolved_lexicon_candidate: bool = False
    extra_signals: dict[str, float | bool | str | None] = field(default_factory=dict)
    mean_token_log_probability: float | None = None


def load_quality_gate_settings(path: str | Path) -> QualityGateSettings:
    config_path = Path(path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        quality = data["quality_gate"]
        thresholds = quality["thresholds"]
        settings = QualityGateSettings(
            high_risk_threshold=float(quality["high_risk_threshold"]),
            min_chars_per_second=float(thresholds["min_chars_per_second"]),
            max_chars_per_second=float(thresholds["max_chars_per_second"]),
            min_density_audio_s=float(thresholds["min_density_audio_s"]),
            unexpected_latin_ratio=float(thresholds["unexpected_latin_ratio"]),
            min_unexpected_latin_chars=int(thresholds["min_unexpected_latin_chars"]),
            min_boundary_overlap_s=float(thresholds["min_boundary_overlap_s"]),
            disagreement_threshold=float(thresholds["disagreement_threshold"]),
            min_mean_token_log_probability=float(
                thresholds["min_mean_token_log_probability"]),
            weights={name: float(value) for name, value in quality["weights"].items()},
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid quality gate config {config_path}") from exc
    return validate_quality_gate_settings(settings, str(config_path))


def validate_quality_gate_settings(
        settings: QualityGateSettings, source: str = "settings") -> QualityGateSettings:
    ratios = (
        settings.high_risk_threshold,
        settings.unexpected_latin_ratio,
        settings.disagreement_threshold,
    )
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in ratios):
        raise ValueError(f"invalid quality gate config {source}: ratios must be between 0 and 1")
    durations = (
        settings.min_chars_per_second,
        settings.max_chars_per_second,
        settings.min_density_audio_s,
        settings.min_boundary_overlap_s,
    )
    if any(not math.isfinite(value) or value < 0 for value in durations):
        raise ValueError(f"invalid quality gate config {source}: thresholds must be non-negative")
    if settings.max_chars_per_second < settings.min_chars_per_second:
        raise ValueError(f"invalid quality gate config {source}: invalid character density range")
    if settings.min_unexpected_latin_chars < 1:
        raise ValueError(f"invalid quality gate config {source}: invalid Latin character minimum")
    if not math.isfinite(settings.min_mean_token_log_probability):
        raise ValueError(f"invalid quality gate config {source}: invalid token log probability")
    if set(settings.weights) != set(_DEFAULT_WEIGHTS):
        raise ValueError(f"invalid quality gate config {source}: risk weights do not match known reasons")
    if any(not math.isfinite(value) or value < 0 for value in settings.weights.values()):
        raise ValueError(f"invalid quality gate config {source}: weights must be finite and non-negative")
    return settings


def _normalized_text(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKC", text).casefold()
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def _digits(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\d+(?:\.\d+)?", unicodedata.normalize("NFKC", text)))


def _edit_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def normalized_disagreement(left: str, right: str) -> float:
    left_norm, right_norm = _normalized_text(left), _normalized_text(right)
    size = max(len(left_norm), len(right_norm))
    return _edit_distance(left_norm, right_norm) / size if size else 0.0


def _excessive_repetition(text: str) -> bool:
    value = _normalized_text(text)
    if re.search(r"(.)\1{3,}", value):
        return True
    return any(re.search(rf"({pattern})\1\1", value)
               for pattern in (r".{2}", r".{3,8}", r".{9,20}"))


class QualityGate:
    def __init__(self, settings: QualityGateSettings):
        self.settings = validate_quality_gate_settings(settings)

    def assess(self, context: QualityContext) -> QualityAssessment:
        text = _normalized_text(context.text)
        raw_text = context.raw_text if context.raw_text is not None else context.text
        raw_audio_s = float(context.audio_s)
        audio_s = raw_audio_s if math.isfinite(raw_audio_s) and raw_audio_s > 0 else 0.0
        chars_per_second = len(text) / audio_s if audio_s else 0.0
        letters = [char for char in text if char.isalpha()]
        latin_chars = sum(char.isascii() and char.isalpha() for char in letters)
        japanese_chars = sum(
            "぀" <= char <= "ヿ" or "一" <= char <= "鿿" for char in letters)
        latin_ratio = latin_chars / len(letters) if letters else 0.0
        signals: dict[str, float | bool | str | None] = {
            "chars_per_second": chars_per_second,
            "latin_ratio": latin_ratio,
            "latin_chars": float(latin_chars),
            "japanese_chars": float(japanese_chars),
            "boundary_overlap_s": (
                float(context.boundary_overlap_s)
                if math.isfinite(float(context.boundary_overlap_s))
                and context.boundary_overlap_s > 0 else 0.0
            ),
        }
        mean_token_log_probability = context.mean_token_log_probability
        if (mean_token_log_probability is not None
                and math.isfinite(mean_token_log_probability)):
            signals["mean_token_log_probability"] = mean_token_log_probability
        else:
            mean_token_log_probability = None
        signals.update(context.extra_signals)
        reasons: list[str] = []

        def add(reason: str, condition: bool) -> None:
            if condition:
                reasons.append(reason)

        add("empty_output", not text)
        density_is_meaningful = audio_s >= self.settings.min_density_audio_s and bool(text)
        add("very_low_chars_per_second",
            density_is_meaningful and chars_per_second < self.settings.min_chars_per_second)
        add("very_high_chars_per_second",
            density_is_meaningful and chars_per_second > self.settings.max_chars_per_second)
        add("excessive_repetition", _excessive_repetition(context.text))
        add("unexpected_latin_ratio", context.lang == "ja"
            and latin_chars >= self.settings.min_unexpected_latin_chars
            and latin_ratio >= self.settings.unexpected_latin_ratio
            and japanese_chars < 4)
        add("boundary_forced_split", context.forced_split)
        add("short_boundary_overlap", context.forced_split
            and 0 < context.boundary_overlap_s < self.settings.min_boundary_overlap_s)
        add("digit_loss", bool(_digits(raw_text)) and _digits(raw_text) != _digits(context.text))
        add("suspicious_single_character", audio_s >= self.settings.min_density_audio_s
            and len(text) == 1)
        add("unresolved_lexicon_candidate", context.unresolved_lexicon_candidate)
        add("low_token_log_probability", mean_token_log_probability is not None
            and mean_token_log_probability < self.settings.min_mean_token_log_probability)

        if context.refined_text is not None:
            disagreement = normalized_disagreement(context.text, context.refined_text)
            signals["primary_refine_disagreement"] = disagreement
            add("primary_refine_disagreement", disagreement >= self.settings.disagreement_threshold)
        if context.secondary_text is not None:
            disagreement = normalized_disagreement(context.text, context.secondary_text)
            signals["secondary_disagreement"] = disagreement
            add("secondary_disagreement", disagreement >= self.settings.disagreement_threshold)

        score = min(1.0, sum(self.settings.weights[reason] for reason in reasons))
        signals["high_risk"] = score >= self.settings.high_risk_threshold
        return QualityAssessment(score, tuple(reasons), signals)
