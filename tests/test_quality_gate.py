"""Model-free tests for Japanese structured results and quality risk signals."""

import json
import os
import sys

import pytest
import numpy as np


sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from japanese_types import DecodeResult, QualityAssessment
import asr_engine
from quality_gate import (QualityContext, QualityGate, QualityGateSettings,
                          load_quality_gate_settings, normalized_disagreement)


def gate(**overrides):
    return QualityGate(QualityGateSettings(**overrides))


def test_normal_japanese_is_low_risk():
    result = gate().assess(QualityContext("今日は東京へ行きます", 2.5))
    assert result.risk_score == 0
    assert result.risk_reasons == ()
    assert result.risk_signals["high_risk"] is False


def test_empty_output_is_explainable_high_risk():
    result = gate().assess(QualityContext("", 2.0))
    assert result.risk_score == 1.0
    assert result.risk_reasons == ("empty_output",)
    assert result.risk_signals["high_risk"] is True


@pytest.mark.parametrize("text,audio_s,reason", [
    ("短い", 5.0, "very_low_chars_per_second"),
    ("あ" * 30, 1.0, "very_high_chars_per_second"),
    ("テストテストテスト", 2.0, "excessive_repetition"),
    ("AAAAAAAAAAAA", 2.0, "unexpected_latin_ratio"),
    ("あ", 2.0, "suspicious_single_character"),
])
def test_basic_risk_reasons(text, audio_s, reason):
    result = gate().assess(QualityContext(text, audio_s))
    assert reason in result.risk_reasons


def test_normal_mixed_japanese_product_name_is_not_unexpected_latin():
    result = gate().assess(QualityContext("GitHub Actionsを使います", 3.0))
    assert "unexpected_latin_ratio" not in result.risk_reasons


def test_digit_loss_compares_raw_and_display_text():
    result = gate().assess(QualityContext("開始は午後です", 2.0, raw_text="開始は15時です"))
    assert "digit_loss" in result.risk_reasons


def test_model_specific_token_log_probability_is_risk_not_confidence():
    result = gate().assess(QualityContext(
        "文章です", 1.0, mean_token_log_probability=-0.3))
    assert "low_token_log_probability" in result.risk_reasons
    assert result.risk_signals["mean_token_log_probability"] == -0.3
    assert not any("confidence" in key for key in result.risk_signals)


def test_boundary_reasons_include_short_overlap_only_when_forced():
    result = gate().assess(QualityContext(
        "続きです", 2.0, forced_split=True, boundary_overlap_s=0.1))
    assert "boundary_forced_split" in result.risk_reasons
    assert "short_boundary_overlap" in result.risk_reasons
    ordinary = gate().assess(QualityContext(
        "続きです", 2.0, forced_split=False, boundary_overlap_s=0.1))
    assert "short_boundary_overlap" not in ordinary.risk_reasons


def test_disagreements_are_normalized_and_thresholded():
    assert normalized_disagreement("今日は、東京です。", "今日は東京です") == 0
    result = gate().assess(QualityContext(
        "今日は東京です", 2.0,
        refined_text="明日は大阪へ行きます",
        secondary_text="今日は京都です",
    ))
    assert "primary_refine_disagreement" in result.risk_reasons
    assert result.risk_signals["primary_refine_disagreement"] > 0.35
    assert "secondary_disagreement" not in result.risk_reasons


def test_unknown_extra_signal_is_preserved_but_not_scored():
    result = gate().assess(QualityContext(
        "正常な文章です", 2.0, extra_signals={"future_signal": 0.9}))
    assert result.risk_score == 0
    assert result.risk_signals["future_signal"] == 0.9


def test_non_finite_optional_inputs_degrade_without_invalid_json_numbers():
    result = gate().assess(QualityContext(
        "正常な文章です", float("nan"), boundary_overlap_s=float("inf"),
        mean_token_log_probability=float("nan"),
    ))
    assert result.risk_signals["chars_per_second"] == 0.0
    assert result.risk_signals["boundary_overlap_s"] == 0.0
    assert "mean_token_log_probability" not in result.risk_signals
    assert "low_token_log_probability" not in result.risk_reasons


def test_score_is_capped_at_one():
    result = gate().assess(QualityContext(
        "AAAAAAAAAAAA", 10.0, raw_text="1234", forced_split=True,
        boundary_overlap_s=0.1, refined_text="別の文章です",
        unresolved_lexicon_candidate=True,
    ))
    assert result.risk_score == 1.0


def test_quality_assessment_serializes_lists_not_tuples():
    result = QualityAssessment(0.4, ("digit_loss",), {"high_risk": True})
    assert result.as_dict() == {
        "risk_score": 0.4,
        "risk_reasons": ["digit_loss"],
        "risk_signals": {"high_risk": True},
    }


def test_decode_result_defaults_are_immutable_values():
    result = DecodeResult(raw_text="生", text="表示")
    assert result.tokens == ()
    assert result.timestamps == ()
    assert result.token_log_probs == ()


def test_decode_result_preserves_only_available_sherpa_metadata():
    class Result:
        text = "［東京］です"
        lang = ""
        tokens = ["tok-a", "tok-b"]
        timestamps = [0.0, 0.4]
        ys_log_probs = [-0.1, -0.2]
        emotion = ""
        event = ""
        durations = []
        segment_durations = []
        segment_texts = []
        segment_timestamps = []
        words = []

    class Stream:
        result = Result()

        def accept_waveform(self, sample_rate, samples):
            assert sample_rate == 16000

    class Recognizer:
        def create_stream(self):
            return Stream()

        def decode_stream(self, stream):
            pass

    result = asr_engine.RoutedASR._decode_result(
        Recognizer(), np.zeros(160, dtype=np.float32), 16000)
    assert result.raw_text == "東京です"
    assert result.tokens == ("tok-a", "tok-b")
    assert result.timestamps == (0.0, 0.4)
    assert result.token_log_probs == (-0.1, -0.2)
    assert result.metadata == {}
    assert asr_engine.RoutedASR._decode_full(
        Recognizer(), np.zeros(160, dtype=np.float32), 16000) == ("東京です", "")


def test_quality_config_loads_and_rejects_unknown_weight(tmp_path):
    source = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "configs", "japanese.default.json",
    )
    settings = load_quality_gate_settings(source)
    assert settings.high_risk_threshold == 0.35
    data = json.loads(open(source, encoding="utf-8").read())
    data["quality_gate"]["weights"]["invented_confidence"] = 1.0
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="risk weights"):
        load_quality_gate_settings(bad)
