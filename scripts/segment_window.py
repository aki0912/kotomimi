"""Build bounded ASR audio windows around VAD speech segments.

This module contains no ASR or VAD dependency.  It only reads the rolling
history interface used by ``realtime_transcribe.AudioHistory``.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Protocol

import numpy as np


class AudioHistoryView(Protocol):
    sr: int
    buf: np.ndarray
    offset: int


@dataclass(frozen=True)
class AudioWindow:
    samples: np.ndarray
    sample_rate: int
    speech_start: int
    speech_end: int
    context_start: int
    context_end: int
    overlap_with_previous_samples: int
    forced_split: bool = False

    @property
    def speech_duration_s(self) -> float:
        return (self.speech_end - self.speech_start) / self.sample_rate

    @property
    def overlap_with_previous_s(self) -> float:
        return self.overlap_with_previous_samples / self.sample_rate


@dataclass(frozen=True)
class JapaneseOverlapSettings:
    enabled: bool
    pre_context_s: float
    post_context_s: float
    max_overlap_s: float
    min_overlap_chars: int
    max_overlap_chars: int
    min_similarity: float


def load_japanese_overlap_settings(path: str | Path) -> JapaneseOverlapSettings:
    """Load and strictly validate the PR 2 sections of the Japanese config."""
    config_path = Path(path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read Japanese config {config_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Japanese config {config_path}: {exc.msg}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError(f"invalid Japanese config {config_path}: schema_version must be 1")
    try:
        audio = data["audio"]
        merge = data["text_merge"]
        settings = JapaneseOverlapSettings(
            enabled=merge["enabled"],
            pre_context_s=float(audio["pre_context_s"]),
            post_context_s=float(audio["post_context_s"]),
            max_overlap_s=float(audio["max_overlap_s"]),
            min_overlap_chars=merge["min_overlap_chars"],
            max_overlap_chars=merge["max_overlap_chars"],
            min_similarity=float(merge["min_similarity"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid Japanese config {config_path}: missing or invalid PR 2 field") from exc
    return validate_japanese_overlap_settings(settings, str(config_path))


def validate_japanese_overlap_settings(
        settings: JapaneseOverlapSettings, source: str = "settings") -> JapaneseOverlapSettings:
    if not isinstance(settings.enabled, bool):
        raise ValueError(f"invalid Japanese config {source}: text_merge.enabled must be boolean")
    durations = (settings.pre_context_s, settings.post_context_s, settings.max_overlap_s)
    if any(not math.isfinite(value) or value < 0 for value in durations):
        raise ValueError(f"invalid Japanese config {source}: context values must be finite and non-negative")
    if (isinstance(settings.min_overlap_chars, bool)
            or isinstance(settings.max_overlap_chars, bool)
            or not isinstance(settings.min_overlap_chars, int)
            or not isinstance(settings.max_overlap_chars, int)
            or settings.min_overlap_chars < 1
            or settings.max_overlap_chars < settings.min_overlap_chars):
        raise ValueError(f"invalid Japanese config {source}: invalid overlap character bounds")
    if not math.isfinite(settings.min_similarity) or not 0 <= settings.min_similarity <= 1:
        raise ValueError(f"invalid Japanese config {source}: min_similarity must be between 0 and 1")
    return settings


class SegmentWindowBuilder:
    """Stateful window builder whose state is only prior window boundaries."""

    def __init__(self):
        self._previous_context_start: int | None = None
        self._previous_context_end: int | None = None
        self._previous_speech_end: int | None = None

    def reset(self) -> None:
        self._previous_context_start = None
        self._previous_context_end = None
        self._previous_speech_end = None

    def build(
        self,
        *,
        history: AudioHistoryView,
        speech_start: int,
        speech_end: int,
        speech_samples: np.ndarray,
        pre_context_s: float,
        post_context_s: float,
        max_overlap_s: float,
        allow_previous_overlap: bool,
        forced_split: bool,
    ) -> AudioWindow:
        if speech_start < 0 or speech_end < speech_start:
            raise ValueError("invalid speech sample bounds")
        if len(speech_samples) != speech_end - speech_start:
            raise ValueError("speech_samples length does not match speech bounds")
        if history.sr <= 0:
            raise ValueError("sample rate must be positive")
        if min(pre_context_s, post_context_s, max_overlap_s) < 0:
            raise ValueError("context durations must be non-negative")

        sample_rate = history.sr
        history_start = history.offset
        history_end = history.offset + len(history.buf)
        pre_samples = int(round(pre_context_s * sample_rate))
        post_samples = int(round(post_context_s * sample_rate))
        max_overlap_samples = int(round(max_overlap_s * sample_rate))

        desired_start = max(speech_start - pre_samples, history_start)
        if self._previous_context_end is not None:
            if allow_previous_overlap:
                # max_overlap_s limits duplicated *speech*.  The previous
                # context end can include post-VAD silence, so measuring the
                # allowance from it would silently consume post_context_s
                # (for example, 0.3 s max - 0.2 s post = only 0.1 s of
                # reusable speech) and leave too little audio for text
                # alignment.  Anchor the limit at the prior speech end.
                previous_overlap_end = (
                    self._previous_speech_end
                    if self._previous_speech_end is not None
                    else self._previous_context_end
                )
                desired_start = max(
                    desired_start,
                    previous_overlap_end - max_overlap_samples,
                )
            else:
                desired_start = max(desired_start, self._previous_context_end)
        context_start = min(desired_start, speech_start)
        context_end = min(speech_end + post_samples, history_end)
        context_end = max(context_end, speech_end)

        pre = history.buf[
            max(context_start - history_start, 0):
            max(speech_start - history_start, 0)
        ]
        available_post_start = max(speech_end - history_start, 0)
        available_post_end = max(context_end - history_start, 0)
        post = history.buf[available_post_start:available_post_end]
        samples = np.concatenate((pre, speech_samples, post))

        # Metadata must describe the samples actually returned.  The speech
        # core comes from VAD even if a rolling history edge clipped context.
        context_start = speech_start - len(pre)
        context_end = speech_end + len(post)
        overlap = 0
        if self._previous_context_start is not None and self._previous_speech_end is not None:
            # Only duplicated prior speech can produce duplicated text.  Do
            # not authorize text deletion when the two windows share merely
            # post-VAD silence.
            overlap = max(
                0,
                min(self._previous_speech_end, context_end)
                - max(self._previous_context_start, context_start),
            )

        window = AudioWindow(
            samples=samples,
            sample_rate=sample_rate,
            speech_start=speech_start,
            speech_end=speech_end,
            context_start=context_start,
            context_end=context_end,
            overlap_with_previous_samples=overlap,
            forced_split=forced_split,
        )
        self._previous_context_start = context_start
        self._previous_context_end = context_end
        self._previous_speech_end = speech_end
        return window
