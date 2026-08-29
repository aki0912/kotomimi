from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import tarfile
import wave

import pytest

import kotomimi_eval.datasets.fleurs as fleurs_module

from kotomimi_eval.datasets.fleurs import (
    AUDIO_REPO_PATH,
    TSV_REPO_PATH,
    _read_tsv,
    download_fleurs,
    prepare_fleurs,
    verify_prepared_fleurs,
)
from kotomimi_eval.errors import DatasetPreparationError, ModelEvaluationUnavailable
from kotomimi_eval.evaluation import hayamimi_adapter
from kotomimi_eval.evaluation.hayamimi_adapter import HayamimiAdapter
from kotomimi_eval.hashing import sha256_file
from kotomimi_eval.licensing.registry import load_registry
from kotomimi_eval.prepare.manifest import load_manifest, write_json_atomic


def _wav_bytes(frequency: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        samples = [int(4000 * ((index * frequency // 16000) % 2 * 2 - 1)) for index in range(16000)]
        handle.writeframes(b"".join(struct.pack("<h", value) for value in samples))
    return output.getvalue()


def _fixture_record():
    base = load_registry().get("fleurs_ja")
    raw = dict(base.raw)
    raw["source_revision"] = "fixture-revision"
    raw["source_config"] = "ja_jp"
    return replace(base, version="fixture-revision", expected={"rows": 2}, raw=raw)


def _fixture_download(data_root: Path, record):
    directory = data_root / "downloads" / record.dataset_id / record.version
    directory.mkdir(parents=True)
    tsv = directory / "test.tsv"
    tsv.write_text(
        "100\tfirst.wav\tＡＩは、便利です。\tAIは 便利です\tＡ Ｉ は | 便 利 で す |\t16000\tFEMALE\n"
        "101\tsecond.wav\t今日は東京です。\t今日は東京です\t今 日 は 東 京 で す |\t16000\tMALE\n",
        encoding="utf-8")
    archive = directory / "test.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        for filename, frequency in (("first.wav", 220), ("second.wav", 330)):
            data = _wav_bytes(frequency)
            info = tarfile.TarInfo(f"test/{filename}")
            info.size = len(data)
            handle.addfile(info, io.BytesIO(data))
    receipt = {
        "schema_version": 1,
        "dataset_id": record.dataset_id,
        "source_repo": "google/fleurs",
        "source_revision": record.raw["source_revision"],
        "source_config": "ja_jp",
        "source_split": "test",
        "files": {
            TSV_REPO_PATH: {"filename": "test.tsv", "sha256": sha256_file(tsv), "size": tsv.stat().st_size},
            AUDIO_REPO_PATH: {"filename": "test.tar.gz", "sha256": sha256_file(archive), "size": archive.stat().st_size},
        },
    }
    write_json_atomic(directory / "download.receipt.json", receipt)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_fleurs_fixture_prepares_reproducible_manifest_without_mutating_raw(tmp_path):
    record = _fixture_record()
    _fixture_download(tmp_path, record)
    first = prepare_fleurs(record, tmp_path)
    rows = load_manifest(first.manifest_path)
    assert first.row_count == 2
    assert rows[0]["reference_raw"] == "ＡＩは、便利です。"
    assert rows[0]["reference_nfc"] == "ＡＩは、便利です。"
    assert rows[0]["reference_eval"] == "aiは便利です"
    assert rows[0]["metadata"]["source_transcription"] == "AIは 便利です"
    assert rows[0]["sample_rate"] == 16000
    assert rows[0]["channels"] == 1
    assert rows[0]["audio_path"].endswith(".flac")
    assert len(rows[0]["source_audio_sha256"]) == 64
    assert len(rows[0]["audio_sha256"]) == 64
    assert rows[0]["source_audio_sha256"] != rows[0]["audio_sha256"]
    lock = json.loads(first.lock_path.read_text(encoding="utf-8"))
    assert lock["row_count"] == 2
    assert lock["source_revision"] == "fixture-revision"
    second = prepare_fleurs(record, tmp_path)
    assert second.manifest_sha256 == first.manifest_sha256
    assert verify_prepared_fleurs(record, tmp_path).manifest_sha256 == first.manifest_sha256


def test_fleurs_row_count_mismatch_is_hard_failure(tmp_path):
    tsv = tmp_path / "test.tsv"
    tsv.write_text(
        "100\tone.wav\t正解です。\t正解です\t正 解 で す |\t16000\tMALE\n",
        encoding="utf-8")
    with pytest.raises(DatasetPreparationError, match="row count changed"):
        _read_tsv(tsv, expected_rows=2)


def test_fleurs_tsv_requires_exact_columns(tmp_path):
    tsv = tmp_path / "test.tsv"
    tsv.write_text("too\tfew\tcolumns\n", encoding="utf-8")
    with pytest.raises(DatasetPreparationError, match="expected 7"):
        _read_tsv(tsv, expected_rows=1)


def test_download_always_passes_pinned_revision(tmp_path, monkeypatch):
    record = load_registry().get("fleurs_ja")
    cache = tmp_path / "cache"
    cache.mkdir()
    files = {
        TSV_REPO_PATH: cache / "test.tsv",
        AUDIO_REPO_PATH: cache / "test.tar.gz",
    }
    files[TSV_REPO_PATH].write_text("fixture", encoding="utf-8")
    files[AUDIO_REPO_PATH].write_bytes(b"archive")
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        return str(files[kwargs["filename"]])

    monkeypatch.setattr(fleurs_module, "hf_hub_download", fake_download)
    receipt = download_fleurs(record, tmp_path / "data")
    assert len(calls) == 2
    assert all(call["revision"] == record.raw["source_revision"] for call in calls)
    assert all(call["repo_id"] == "google/fleurs" for call in calls)
    assert receipt["source_revision"] == record.raw["source_revision"]


def test_model_adapter_degrades_clearly_when_model_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(hayamimi_adapter, "MODEL_DIR", tmp_path / "missing-model")
    assert not HayamimiAdapter.available()
    with pytest.raises(ModelEvaluationUnavailable, match="download_models.py --minimal"):
        HayamimiAdapter(threads=1, punctuate=False)


@pytest.mark.skipif(
    os.environ.get("KOTOMIMI_RUN_DATASET_TESTS") != "1",
    reason="set KOTOMIMI_RUN_DATASET_TESTS=1 for pinned FLEURS download",
)
def test_pinned_fleurs_download_has_expected_hashable_files(tmp_path):
    receipt = download_fleurs(load_registry().get("fleurs_ja"), tmp_path)
    assert receipt["source_revision"] == "70bb2e84b976b7e960aa89f1c648e09c59f894dd"
    assert receipt["files"][TSV_REPO_PATH]["size"] > 0
    assert receipt["files"][AUDIO_REPO_PATH]["size"] > 0


@pytest.mark.skipif(
    os.environ.get("KOTOMIMI_RUN_MODEL_EVAL") != "1",
    reason="set KOTOMIMI_RUN_MODEL_EVAL=1 for model-backed evaluation",
)
def test_model_is_available_for_optional_evaluation():
    assert HayamimiAdapter.available()
