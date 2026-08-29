import os
import sys

from kotomimi_eval.evaluation.metrics import aggregate_rows, edit_counts


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from eval_common import edit_counts as legacy_edit_counts


def test_normalized_edit_counts_match_existing_eval_common_on_fixture():
    reference = "今日は、東京で会議です。"
    hypothesis = "今日は東京で会義です"
    current = edit_counts(reference, hypothesis, normalize=True)
    legacy = legacy_edit_counts(reference, hypothesis, normalize=True)
    assert (current.substitutions, current.deletions, current.insertions, current.reference_chars) == (
        legacy.substitutions, legacy.deletions, legacy.insertions, legacy.reference_length)


def test_raw_and_normalized_cer_are_reported_separately():
    raw = edit_counts("Ａです。", "Aです", normalize=False)
    normalized = edit_counts("Ａです。", "Aです", normalize=True)
    assert raw.errors == 2
    assert normalized.errors == 0


def test_micro_aggregation_uses_total_characters_not_mean_clip_cer():
    rows = [
        {"raw_substitutions": 1, "raw_deletions": 0, "raw_insertions": 0,
         "raw_reference_chars": 1, "normalized_substitutions": 1,
         "normalized_deletions": 0, "normalized_insertions": 0,
         "normalized_reference_chars": 1, "sentence_exact": False,
         "audio_s": 1.0, "latency_ms": 10.0, "rss_bytes": 100, "failure": None},
        {"raw_substitutions": 0, "raw_deletions": 0, "raw_insertions": 0,
         "raw_reference_chars": 9, "normalized_substitutions": 0,
         "normalized_deletions": 0, "normalized_insertions": 0,
         "normalized_reference_chars": 9, "sentence_exact": True,
         "audio_s": 1.0, "latency_ms": 10.0, "rss_bytes": 120, "failure": None},
    ]
    metrics = aggregate_rows(rows)
    assert metrics["normalized"]["cer"] == 0.1
    assert metrics["sentence_exact_rate"] == 0.5
