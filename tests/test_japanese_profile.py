"""Model-free regression tests for the PR 1 Japanese-only profile."""

import os
import subprocess
import sys

import numpy as np
import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import asr_engine
import download_models
from realtime_transcribe import AudioHistory, PartialPrinter, Refiner, startup_profile


def _fake_japanese_runtime(monkeypatch):
    recognizer = object()
    monkeypatch.setattr(asr_engine, "_build_lid", lambda threads: pytest.fail(
        "fixed Japanese mode must not construct LID"))
    monkeypatch.setattr(asr_engine, "_model_present", lambda name: name == "rz")
    monkeypatch.setattr(asr_engine, "_build_reazon", lambda threads, hotwords: recognizer)
    monkeypatch.setattr(asr_engine.RoutedASR, "_decode",
                        staticmethod(lambda rec, samples, sample_rate: "日本語です"))
    return recognizer


def test_forced_japanese_constructs_only_reazon_and_disables_preload(monkeypatch):
    recognizer = _fake_japanese_runtime(monkeypatch)

    def unexpected_thread(*args, **kwargs):
        pytest.fail("fixed Japanese mode must not start the preload worker")

    monkeypatch.setattr(asr_engine.threading, "Thread", unexpected_thread)
    asr = asr_engine.RoutedASR(
        forced_lang="ja", warmup=True, preload=True, punctuate=False)

    assert asr.lid is None
    assert asr.resident_models == ["rz"]
    assert asr._models["rz"] is recognizer


def test_balanced_profile_still_constructs_lid(monkeypatch):
    lid = object()
    monkeypatch.setattr(asr_engine, "_build_lid", lambda threads: lid)
    asr = asr_engine.RoutedASR(warmup=False, preload=False, punctuate=False)
    assert asr.lid is lid


def test_balanced_profile_still_starts_preload_worker(monkeypatch):
    started = []
    monkeypatch.setattr(asr_engine, "_build_lid", lambda threads: object())

    class FakeThread:
        def __init__(self, target, daemon):
            assert daemon is True
            self.target = target

        def start(self):
            started.append(self.target)

    monkeypatch.setattr(asr_engine.threading, "Thread", FakeThread)
    asr = asr_engine.RoutedASR(warmup=False, preload=True, punctuate=False)
    assert len(started) == 1
    assert started[0].__self__ is asr


def test_non_japanese_single_route_keeps_existing_fallback_policy():
    class Stub:
        def _route(self, lang):
            assert lang == "en"
            return "fallback-recognizer", "rz"

    assert asr_engine.RoutedASR._route_forced(Stub(), "en") == (
        "fallback-recognizer", "rz")


def test_identify_lang_fails_explicitly_when_disabled(monkeypatch):
    _fake_japanese_runtime(monkeypatch)
    asr = asr_engine.RoutedASR(
        forced_lang="ja", warmup=False, preload=False, punctuate=False)
    with pytest.raises(RuntimeError, match="language identification is disabled"):
        asr._identify_lang(np.zeros(1600, dtype=np.float32), 16000)


def test_forced_japanese_partial_and_transcribe_never_use_other_tier(monkeypatch):
    _fake_japanese_runtime(monkeypatch)
    asr = asr_engine.RoutedASR(
        forced_lang="ja", warmup=False, preload=True, punctuate=False)

    samples = np.zeros(1600, dtype=np.float32)
    assert asr.partial(samples, 16000) == "日本語です"
    result = asr.transcribe(samples, 16000, live=True)

    assert result["text"] == "日本語です"
    assert result["lang"] == "ja"
    assert result["tier"] == "rz"
    assert set(result) == {"text", "lang", "tier", "lid_ms", "decode_ms", "probe_ms"}
    structured = asr.transcribe(samples, 16000, live=True, structured=True)
    assert structured["raw_text"] == "日本語です"
    assert structured["decode_result"].text == "日本語です"
    assert asr.resident_models == ["rz"]


def test_forced_japanese_missing_reazon_does_not_fallback(monkeypatch):
    monkeypatch.setattr(asr_engine, "_build_lid", lambda threads: pytest.fail(
        "fixed Japanese mode must not construct LID"))
    monkeypatch.setattr(asr_engine, "_model_present", lambda name: False)
    asr = asr_engine.RoutedASR(
        forced_lang="ja", warmup=False, preload=False, punctuate=False)

    with pytest.raises(RuntimeError, match="requires ReazonSpeech"):
        asr.transcribe(np.zeros(1600, dtype=np.float32), 16000)
    assert asr.resident_models == []


def test_missing_optional_punctuation_degrades_with_clear_warning(
        monkeypatch, capsys):
    _fake_japanese_runtime(monkeypatch)
    monkeypatch.setitem(sys.modules, "punct_ja", None)
    asr = asr_engine.RoutedASR(
        forced_lang="ja", warmup=False, preload=False, punctuate=True)

    assert asr.punct is None
    assert asr._punctuate is False
    assert "continuing without punctuation" in capsys.readouterr().err


def test_forced_japanese_refiner_does_not_reenable_lid():
    class FakeAsr:
        forced_lang = "ja"

        def __init__(self):
            self.calls = 0

        def _identify_lang(self, buf, sample_rate):
            raise AssertionError("Japanese refiner must not call LID")

        def _get(self, name):
            raise AssertionError("Japanese refiner must not load another ASR tier")

        def transcribe(self, buf, sample_rate, known_lang=None, live=False):
            self.calls += 1
            assert known_lang == "ja"
            return {"text": "日本語の清書です"}

    sample_rate = 16000
    history = AudioHistory(sample_rate, keep_s=10.0)
    history.push(np.zeros(sample_rate * 3, dtype=np.float32))
    asr = FakeAsr()
    refiner = Refiner(asr, history, sample_rate, PartialPrinter(enabled=False))
    refiner.add_span(0, sample_rate * 3 // 2, "ja", "日本語の速報です", "")
    # ASCII-heavy output would normally create a language boundary and later
    # trigger SV probing. A fixed profile must keep one ja-only group.
    refiner.add_span(sample_rate * 3 // 2, sample_rate * 3,
                     "ja", "HELLO TELASA 100M", "")
    refiner.maybe_refine(sample_rate * 3, force=True, force_sync=True)

    assert asr.calls == 1


def test_japanese_startup_profile_is_stable():
    assert startup_profile("single", "ja") == (
        "profile=japanese forced_lang=ja lid=disabled preload=rz-only")
    assert startup_profile("balanced", None) is None


def test_single_mode_requires_language_before_model_loading():
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "realtime_transcribe.py"),
         "--mode", "single"],
        cwd=ROOT, capture_output=True, text=True, check=False)
    assert proc.returncode == 2
    assert "--mode single requires --lang CODE" in proc.stderr
    assert "loading models" not in proc.stderr


def test_japanese_only_download_set_excludes_lid_and_other_languages(
        monkeypatch, tmp_path, capsys):
    labels = []

    def record(*args, **kwargs):
        labels.append(args[-1])

    monkeypatch.setattr(download_models, "MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(download_models, "download_and_extract_tarbz2", record)
    monkeypatch.setattr(download_models, "download_file", record)
    monkeypatch.setattr(download_models, "download_hf_repo", record)
    monkeypatch.setattr(download_models, "extract_members_only", record)

    download_models.main(["--japanese-only"])

    output = capsys.readouterr().out
    assert any("ReazonSpeech" in label for label in labels)
    assert any("Silero VAD" in label for label in labels)
    assert any("punctuation" in label for label in labels)
    assert not any("whisper" in label.lower() for label in labels)
    assert not any(token in label for label in labels
                   for token in ("Paraformer", "SenseVoice", "Parakeet", "Omnilingual"))
    assert "--mode single --lang ja" in output
    assert "This set excludes LID" in output


def test_minimal_download_set_keeps_its_existing_whisper_semantics(
        monkeypatch, tmp_path):
    labels = []

    def record(*args, **kwargs):
        labels.append(args[-1])

    monkeypatch.setattr(download_models, "MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(download_models, "download_and_extract_tarbz2", record)
    monkeypatch.setattr(download_models, "download_file", record)
    monkeypatch.setattr(download_models, "download_hf_repo", record)
    monkeypatch.setattr(download_models, "extract_members_only", record)

    download_models.main(["--minimal"])

    assert any("ReazonSpeech" in label for label in labels)
    assert any("whisper-tiny" in label for label in labels)
    assert any("Silero VAD" in label for label in labels)
    assert any("punctuation" in label for label in labels)
    assert not any(token in label for label in labels
                   for token in ("Paraformer", "SenseVoice", "Parakeet", "Omnilingual"))


@pytest.mark.parametrize("other", ["--minimal", "--eval-baselines"])
def test_japanese_only_download_flag_rejects_conflicting_sets(other):
    with pytest.raises(SystemExit) as exc:
        download_models.main(["--japanese-only", other])
    assert exc.value.code == 2
