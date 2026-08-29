"""Model-free tests for conservative text overlap merging."""

import os
import random
import string
import sys

import pytest


sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from text_overlap import merge_overlapping_text
from subtitle_server import SubtitleServer


def test_exact_japanese_overlap():
    result = merge_overlapping_text(
        "明日は東京都多摩市に", "東京都多摩市に行きます", audio_overlap_s=0.8)
    assert result.merged_text == "明日は東京都多摩市に行きます"
    assert result.current_delta == "行きます"
    assert result.applied


def test_punctuation_difference_preserves_original_spelling():
    result = merge_overlapping_text(
        "今日は、会議です。", "会議です、よろしくお願いします", audio_overlap_s=0.8)
    assert result.merged_text == "今日は、会議です。よろしくお願いします"
    assert result.matched_previous_suffix == "会議です。"
    assert result.matched_current_prefix == "会議です、"


def test_current_boundary_punctuation_is_kept_when_previous_has_none():
    result = merge_overlapping_text(
        "今日は会議です", "会議です。よろしくお願いします", audio_overlap_s=0.8)
    assert result.merged_text == "今日は会議です。よろしくお願いします"
    assert result.current_delta == "。よろしくお願いします"


def test_no_audio_overlap_never_deduplicates():
    result = merge_overlapping_text("東京都多摩市", "東京都多摩市です", audio_overlap_s=0)
    assert result.current_delta == "東京都多摩市です"
    assert result.merged_text == "東京都多摩市東京都多摩市です"
    assert not result.applied


def test_legitimate_short_repetition_is_preserved():
    result = merge_overlapping_text("はい", "はいもう一度説明します", audio_overlap_s=1.0)
    assert result.current_delta == "はいもう一度説明します"
    assert not result.applied


@pytest.mark.parametrize("previous,current", [
    ("はいはい", "はいもう一度説明します"),
    ("そうそう", "そうそうそれです"),
])
def test_deliberate_repetition_is_preserved(previous, current):
    result = merge_overlapping_text(previous, current, audio_overlap_s=1.0)
    assert result.current_delta == current
    assert not result.applied


def test_short_overlap_requires_more_audio():
    result = merge_overlapping_text("こちらですね", "ですね次です", audio_overlap_s=0.3)
    assert result.current_delta == "ですね次です"
    assert not result.applied


def test_english_product_name_overlap_requires_exact_match():
    exact = merge_overlapping_text(
        "GitHub Actionsを", "github actionsを使います", audio_overlap_s=0.8)
    changed = merge_overlapping_text(
        "GitHub Actionsを", "GitLab Actionsを使います", audio_overlap_s=0.8)
    assert exact.merged_text == "GitHub Actionsを使います"
    assert exact.applied
    assert changed.current_delta == "GitLab Actionsを使います"
    assert not changed.applied


def test_nfkc_full_width_product_identifier_matches_exactly():
    result = merge_overlapping_text("型番ＡＢＣ１００を", "ABC100を使います", audio_overlap_s=0.8)
    assert result.merged_text == "型番ＡＢＣ１００を使います"
    assert result.applied


def test_nfkc_half_width_kana_diacritic_keeps_source_index_mapping():
    result = merge_overlapping_text("音声ｶﾞｲﾄﾞを", "ガイドを使います", audio_overlap_s=0.8)
    assert result.merged_text == "音声ｶﾞｲﾄﾞを使います"
    assert result.matched_previous_suffix == "ｶﾞｲﾄﾞを"
    assert result.current_delta == "使います"


def test_numeric_mismatch_is_never_fuzzy_merged():
    result = merge_overlapping_text("バージョン12を", "バージョン13を使います", audio_overlap_s=1.0)
    assert result.current_delta == "バージョン13を使います"
    assert not result.applied


def test_long_japanese_overlap_allows_one_character_asr_difference():
    result = merge_overlapping_text(
        "明日は東京都多摩市役所へ", "東京都多磨市役所へ行きます",
        audio_overlap_s=0.8, min_similarity=0.85)
    assert result.current_delta == "行きます"
    assert result.applied


def test_complete_duplicate_requires_long_audio_overlap():
    short = merge_overlapping_text("もう一度お願いします", "もう一度お願いします", audio_overlap_s=0.3)
    long = merge_overlapping_text("もう一度お願いします", "もう一度お願いします", audio_overlap_s=0.8)
    assert not short.applied
    assert long.applied
    assert long.current_delta == ""


def test_invalid_thresholds_are_rejected():
    with pytest.raises(ValueError):
        merge_overlapping_text("abc", "abc", audio_overlap_s=1, min_overlap_chars=0)
    with pytest.raises(ValueError):
        merge_overlapping_text("abc", "abc", audio_overlap_s=1, min_similarity=1.1)


def test_random_no_audio_overlap_never_changes_current():
    rng = random.Random(20260829)
    alphabet = string.ascii_letters + string.digits + "日本語はいそう"
    for _ in range(200):
        previous = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 30)))
        current = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 30)))
        result = merge_overlapping_text(previous, current, audio_overlap_s=0)
        assert result.current_delta == current
        assert not result.applied


def test_final_event_adds_overlap_fields_without_breaking_legacy_shape():
    server = SubtitleServer.__new__(SubtitleServer)
    events = []
    server.publish = events.append
    server.final("従来テキスト", "ja", "", 12.0, "rz")
    server.final("差分", "ja", "", 13.0, "rz",
                 raw_text="重複部分差分", merged_context_text="従来テキスト差分")
    assert events[0] == {
        "type": "final", "text": "従来テキスト", "lang": "ja",
        "speaker": "", "latency_ms": 12.0, "tier": "rz",
    }
    assert events[1]["text"] == "差分"
    assert events[1]["raw_text"] == "重複部分差分"
    assert events[1]["merged_context_text"] == "従来テキスト差分"
