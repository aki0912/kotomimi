"""Model-free tests for bounded VAD context windows."""

import json
import os
import subprocess
import sys

import numpy as np
import pytest


sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from segment_window import (JapaneseOverlapSettings, SegmentWindowBuilder,
                            load_japanese_overlap_settings)
from realtime_transcribe import (AudioHistory, JapaneseOverlapSession, PartialPrinter,
                                 SessionStats, drain_segments,
                                 resolve_japanese_overlap_settings)


class History:
    def __init__(self, sample_rate=100, offset=0, length=2000):
        self.sr = sample_rate
        self.offset = offset
        self.buf = np.arange(offset, offset + length, dtype=np.float32)


def build(builder, history, start, end, **overrides):
    options = dict(
        history=history,
        speech_start=start,
        speech_end=end,
        speech_samples=np.arange(start, end, dtype=np.float32),
        pre_context_s=1.0,
        post_context_s=0.2,
        max_overlap_s=0.8,
        allow_previous_overlap=True,
        forced_split=False,
    )
    options.update(overrides)
    return builder.build(**options)


def test_first_window_adds_available_pre_and_post_context():
    window = build(SegmentWindowBuilder(), History(), 500, 600)
    assert (window.context_start, window.context_end) == (400, 620)
    assert np.array_equal(window.samples, np.arange(400, 620, dtype=np.float32))
    assert window.overlap_with_previous_samples == 0
    assert window.speech_duration_s == 1.0


def test_post_context_never_zero_pads_beyond_history():
    history = History(length=610)
    window = build(SegmentWindowBuilder(), history, 500, 600)
    assert window.context_end == 610
    assert len(window.samples) == 210
    assert window.samples[-1] == 609


def test_overlap_is_capped_by_max_overlap():
    builder = SegmentWindowBuilder()
    first = build(builder, History(), 500, 600)
    second = build(builder, History(), 650, 750)
    assert first.context_end == 620
    assert second.context_start == 550
    assert second.overlap_with_previous_samples == 50


def test_compatibility_mode_never_reenters_previous_window():
    builder = SegmentWindowBuilder()
    first = build(builder, History(), 500, 600, allow_previous_overlap=False)
    second = build(builder, History(), 650, 750, allow_previous_overlap=False)
    assert second.context_start == first.context_end
    assert second.overlap_with_previous_samples == 0


def test_rolling_history_edge_clamps_only_context_not_speech_core():
    history = History(offset=550, length=500)
    window = build(SegmentWindowBuilder(), history, 500, 600)
    assert window.context_start == 500
    assert window.samples[0] == 500
    assert window.samples[99] == 599
    assert window.context_end == 620


def test_reset_removes_previous_window_constraint():
    builder = SegmentWindowBuilder()
    build(builder, History(), 500, 600)
    builder.reset()
    window = build(builder, History(), 650, 750)
    assert window.context_start == 550
    assert window.overlap_with_previous_samples == 0


def test_forced_split_metadata_is_preserved():
    window = build(SegmentWindowBuilder(), History(), 500, 600, forced_split=True)
    assert window.forced_split is True


@pytest.mark.parametrize("field,value", [
    ("pre_context_s", -0.1),
    ("post_context_s", -0.1),
    ("max_overlap_s", -0.1),
])
def test_negative_context_is_rejected(field, value):
    with pytest.raises(ValueError, match="non-negative"):
        build(SegmentWindowBuilder(), History(), 500, 600, **{field: value})


def test_japanese_overlap_config_loads_pr2_values(tmp_path):
    config = tmp_path / "ja.json"
    config.write_text(json.dumps({
        "schema_version": 1,
        "audio": {"pre_context_s": 0.8, "post_context_s": 0.2, "max_overlap_s": 0.5},
        "text_merge": {"enabled": True, "min_overlap_chars": 3,
                       "max_overlap_chars": 30, "min_similarity": 0.85},
    }), encoding="utf-8")
    settings = load_japanese_overlap_settings(config)
    assert settings.enabled
    assert settings.pre_context_s == 0.8
    assert settings.min_overlap_chars == 3


@pytest.mark.parametrize("mutate", [
    lambda data: data.update(schema_version=2),
    lambda data: data["audio"].update(pre_context_s=-1),
    lambda data: data["text_merge"].update(enabled="yes"),
    lambda data: data["text_merge"].update(min_overlap_chars=0),
    lambda data: data["text_merge"].update(min_similarity=1.1),
])
def test_japanese_overlap_config_rejects_invalid_values(tmp_path, mutate):
    data = {
        "schema_version": 1,
        "audio": {"pre_context_s": 0.8, "post_context_s": 0.2, "max_overlap_s": 0.5},
        "text_merge": {"enabled": True, "min_overlap_chars": 2,
                       "max_overlap_chars": 40, "min_similarity": 0.82},
    }
    mutate(data)
    config = tmp_path / "bad.json"
    config.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid Japanese config"):
        load_japanese_overlap_settings(config)


def test_overlap_session_connects_audio_metadata_to_text_delta():
    settings = JapaneseOverlapSettings(
        enabled=True, pre_context_s=0.6, post_context_s=0.2,
        max_overlap_s=0.8, min_overlap_chars=2,
        max_overlap_chars=40, min_similarity=0.82)
    session = JapaneseOverlapSession(settings, sample_rate=100, max_speech_s=12.0)
    history = History()
    first = session.build_window(history, 500, 600, np.arange(500, 600, dtype=np.float32))
    first_text = session.merge_text("明日は東京都多摩市に", first.overlap_with_previous_s)
    second = session.build_window(history, 650, 750, np.arange(650, 750, dtype=np.float32))
    second_text = session.merge_text("多摩市に行きます", second.overlap_with_previous_s)
    assert first_text.text == "明日は東京都多摩市に"
    assert second.overlap_with_previous_samples > 0
    assert second_text.text == "行きます"
    assert second_text.raw_text == "多摩市に行きます"
    assert second_text.merged_context_text == "明日は東京都多摩市に行きます"
    third = session.build_window(history, 1000, 1100, np.arange(1000, 1100, dtype=np.float32))
    third_text = session.merge_text("別の発話です", third.overlap_with_previous_s)
    assert third.overlap_with_previous_samples == 0
    assert third_text.merged_context_text == "別の発話です"


def test_runtime_config_is_opt_in_and_only_applies_to_single_japanese(tmp_path):
    config = tmp_path / "ja.json"
    config.write_text(json.dumps({
        "schema_version": 1,
        "audio": {"pre_context_s": 0.6, "post_context_s": 0.2, "max_overlap_s": 0.8},
        "text_merge": {"enabled": False, "min_overlap_chars": 2,
                       "max_overlap_chars": 40, "min_similarity": 0.82},
    }), encoding="utf-8")
    common = dict(config_path=str(config), pre_context_s=None, post_context_s=None,
                  max_overlap_s=None, min_similarity=None)
    assert resolve_japanese_overlap_settings(
        mode="single", lang="ja", enabled_override=None, **common) is None
    enabled = resolve_japanese_overlap_settings(
        mode="single", lang="ja", enabled_override=True, **common)
    assert enabled is not None and enabled.enabled
    assert resolve_japanese_overlap_settings(
        mode="balanced", lang=None, enabled_override=True, **common) is None
    with pytest.raises(ValueError, match="non-negative"):
        resolve_japanese_overlap_settings(
            mode="single", lang="ja", enabled_override=True,
            pre_context_s=-0.1, post_context_s=None,
            max_overlap_s=None, min_similarity=None,
            config_path=str(config))


def test_drain_segments_emits_delta_raw_and_merged_context():
    class Segment:
        def __init__(self, start, end):
            self.start = start
            self.samples = np.arange(start, end, dtype=np.float32)

    class Vad:
        def __init__(self):
            self.segments = [Segment(500, 600), Segment(650, 750)]

        def empty(self):
            return not self.segments

        @property
        def front(self):
            return self.segments[0]

        def pop(self):
            self.segments.pop(0)

    class Asr:
        def __init__(self):
            self.texts = iter(["明日は東京都多摩市に", "多摩市に行きます"])

        def transcribe(self, *args, **kwargs):
            return {"text": next(self.texts), "lang": "ja", "tier": "rz",
                    "lid_ms": 0.0, "probe_ms": 0.0, "decode_ms": 1.0}

    class Server:
        def __init__(self):
            self.events = []

        def final(self, *args, **kwargs):
            self.events.append((args, kwargs))

    settings = JapaneseOverlapSettings(
        enabled=True, pre_context_s=0.6, post_context_s=0.2,
        max_overlap_s=0.8, min_overlap_chars=2,
        max_overlap_chars=40, min_similarity=0.82)
    history = AudioHistory(sample_rate=100)
    history.push(np.arange(2000, dtype=np.float32))
    server = Server()
    stats = SessionStats()
    drained = drain_segments(
        Vad(), 100, Asr(), stats, PartialPrinter(enabled=False, server=server),
        history=history,
        overlap_session=JapaneseOverlapSession(settings, 100, 12.0))
    assert drained == 2
    assert server.events[0][0][0] == "明日は東京都多摩市に"
    assert server.events[1][0][0] == "行きます"
    assert server.events[1][1]["raw_text"] == "多摩市に行きます"
    assert server.events[1][1]["merged_context_text"] == "明日は東京都多摩市に行きます"
    assert stats.overlap_merges == 1


def test_drain_segments_keeps_raw_text_when_full_duplicate_has_empty_delta():
    class Segment:
        def __init__(self, start, end):
            self.start = start
            self.samples = np.arange(start, end, dtype=np.float32)

    class Vad:
        def __init__(self):
            self.segments = [Segment(500, 600), Segment(600, 700)]

        def empty(self):
            return not self.segments

        @property
        def front(self):
            return self.segments[0]

        def pop(self):
            self.segments.pop(0)

    class Asr:
        def transcribe(self, *args, **kwargs):
            return {"text": "同じ発話が続きます", "lang": "ja", "tier": "rz",
                    "lid_ms": 0.0, "probe_ms": 0.0, "decode_ms": 1.0}

    class Server:
        def __init__(self):
            self.events = []

        def final(self, *args, **kwargs):
            self.events.append((args, kwargs))

    settings = JapaneseOverlapSettings(
        enabled=True, pre_context_s=1.0, post_context_s=0.0,
        max_overlap_s=1.0, min_overlap_chars=2,
        max_overlap_chars=40, min_similarity=0.82)
    history = AudioHistory(sample_rate=100)
    history.push(np.arange(2000, dtype=np.float32))
    server = Server()
    stats = SessionStats()
    drain_segments(
        Vad(), 100, Asr(), stats, PartialPrinter(enabled=False, server=server),
        history=history,
        overlap_session=JapaneseOverlapSession(settings, 100, 12.0))
    assert len(server.events) == 2
    assert server.events[1][0][0] == ""
    assert server.events[1][1]["raw_text"] == "同じ発話が続きます"
    assert server.events[1][1]["merged_context_text"] == "同じ発話が続きます"
    assert stats.overlap_merges == 1


def test_cli_rejects_invalid_overlap_override_before_loading_models():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, os.path.join(root, "scripts", "realtime_transcribe.py"),
         "--mode", "single", "--lang", "ja", "--ja-overlap",
         "--ja-pre-context", "-0.1"],
        cwd=root, capture_output=True, text=True, check=False)
    assert proc.returncode == 2
    assert "context values must be finite and non-negative" in proc.stderr
    assert "loading models" not in proc.stderr
