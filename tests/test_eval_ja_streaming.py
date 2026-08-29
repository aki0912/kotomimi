"""Model-free tests for the Japanese streaming evaluation harness."""

import json
import os
import sys
import wave

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from eval_common import (abnormal_repetition, digits_exact, edit_counts,
                         normalize_ja, term_counts)
from eval_ja_streaming import (DEFAULT_MODES, Evaluator, ManifestError, load_manifest,
                               main, model_status, render_markdown, score_hypotheses,
                               write_reports)


def test_edit_counts_known_cases():
    counts = edit_counts("今日は東京です。", "今日東京でした")
    assert counts.substitutions == 1
    assert counts.deletions == 1
    assert counts.insertions == 1
    assert counts.distance == 3
    assert counts.reference_length == len(normalize_ja("今日は東京です。"))


def test_edit_counts_boundary_deletions():
    leading = edit_counts("東京都多摩市", "京都多摩市")
    trailing = edit_counts("東京都多摩市", "東京都多摩")
    assert leading.leading_deletion
    assert not leading.trailing_deletion
    assert trailing.trailing_deletion


def test_term_counts_include_false_positive_from_manifest_vocabulary():
    assert term_counts(["多摩市"], "東京都多摩市", ["多摩市", "八王子市"]) == (1, 0, 0)
    assert term_counts(["多摩市"], "八王子市です", ["多摩市", "八王子市"]) == (0, 1, 1)


def test_digits_exact_uses_nfkc_and_order():
    assert digits_exact("１００人が2026年に参加", "100人が2026年に参加", ["100", "2026"])
    assert not digits_exact("100人が2026年に参加", "2026年に100人が参加", ["100", "2026"])


def test_abnormal_repetition():
    assert abnormal_repetition("これはこれはこれは異常です")
    assert not abnormal_repetition("これは普通の文章です")


def test_load_manifest_resolves_relative_wav(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps({
        "id": "ja_001", "wav": "audio/one.wav", "text": "こんにちは",
        "category": "clean_mic", "terms": [], "digits": [],
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    entries = load_manifest(manifest)
    assert entries[0]["wav_path"] == str(tmp_path / "audio/one.wav")


@pytest.mark.parametrize("content, message", [
    ("{bad json}\n", "invalid JSON"),
    (json.dumps({"id": "x"}) + "\n", "missing fields"),
    ("\n", "dataset is empty"),
])
def test_load_manifest_errors(tmp_path, content, message):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(content, encoding="utf-8")
    with pytest.raises(ManifestError, match=message):
        load_manifest(manifest)


def test_score_and_write_all_report_formats(tmp_path):
    entries = [{
        "id": "one", "wav": "one.wav", "wav_path": "one.wav",
        "text": "東京都に100人います", "category": "numbers",
        "terms": ["東京都"], "digits": ["100"],
    }]
    hypotheses = [{
        "id": "one", "mode": mode, "text": "東京都に100人います",
        "audio_s": 2.0, "decode_ms": 100.0, "final_latencies_ms": [80.0, 120.0],
        "max_rss_bytes": 1024 * 1024, "segments": 1,
    } for mode in DEFAULT_MODES]
    metrics = score_hypotheses(entries, hypotheses, DEFAULT_MODES)
    for mode in DEFAULT_MODES:
        overall = metrics["modes"][mode]["overall"]
        assert overall["cer"] == 0.0
        assert overall["term_f1"] == 1.0
        assert overall["digits_exact_rate"] == 1.0
        assert overall["final_latency_ms_p50"] == 100.0

    scored = [{**row, "category": "numbers", "reference": entries[0]["text"], "cer": 0.0}
              for row in hypotheses]
    write_reports(tmp_path / "out", metrics, scored)
    assert json.loads((tmp_path / "out" / "metrics.json").read_text(encoding="utf-8"))["modes"]
    assert len((tmp_path / "out" / "hypotheses.jsonl").read_text(encoding="utf-8").splitlines()) == 4
    report = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "offline_primary" in report
    assert "stream_refine" in report
    assert render_markdown(metrics, scored) == report


def test_cli_skips_cleanly_when_models_are_missing(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps({
        "id": "one", "wav": "missing.wav", "text": "テスト", "category": "clean_mic",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr("eval_ja_streaming.model_status", lambda: (False, ["ReazonSpeech encoder"]))
    assert main(["--manifest", str(manifest)]) == 0
    assert "integration evaluation skipped" in capsys.readouterr().err


_models_available, _missing_models = model_status()


@pytest.mark.skipif(not _models_available, reason="Japanese ASR/VAD models are not downloaded")
def test_offline_integration_when_models_exist(tmp_path):
    wav_path = tmp_path / "silence.wav"
    with wave.open(str(wav_path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\x00\x00" * 16000)
    result = Evaluator(threads=1, min_silence=0.35, max_speech=12.0).offline_primary(str(wav_path))
    assert result.audio_s == 1.0
    assert result.decode_ms >= 0
