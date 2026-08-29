from dataclasses import replace
import hashlib
from pathlib import Path

import numpy as np
import soundfile as sf

from kotomimi_eval.hashing import sha256_file
from kotomimi_eval.licensing.registry import load_registry
from kotomimi_eval.prepare.manifest import load_manifest, write_jsonl_atomic
from kotomimi_eval.qc.runner import run_qc


def fixture_record(row_count: int):
    return replace(load_registry().get("common_voice_ja_26"), expected={"rows": row_count})


def fixture_row(record, prepared: Path, index: int, pcm: np.ndarray, reference: str) -> dict:
    sample_id = f"{index + 1:064x}"
    relative = Path("audio") / sample_id[:2] / f"{sample_id}.flac"
    audio_path = prepared / relative
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(audio_path, pcm, 16000, format="FLAC", subtype="PCM_16")
    pcm_bytes = np.asarray(pcm, dtype="<i2").tobytes()
    return {
        "schema_version": 1,
        "sample_id": sample_id,
        "dataset_id": record.dataset_id,
        "dataset_version": record.version,
        "source_split": "test",
        "source_sample_id": f"clip-{index}.mp3",
        "audio_path": relative.as_posix(),
        "source_audio_path": f"source/clip-{index}.mp3",
        "source_audio_sha256": hashlib.sha256(f"source-{index}".encode()).hexdigest(),
        "audio_sha256": sha256_file(audio_path),
        "pcm_sha256": hashlib.sha256(pcm_bytes).hexdigest(),
        "sample_rate": 16000,
        "channels": 1,
        "duration_s": len(pcm) / 16000,
        "reference_raw": reference,
        "reference_nfc": reference,
        "reference_eval": reference.replace("。", ""),
        "speaker_id": f"{index % 3:064x}",
        "categories": ["read", "common_voice"],
        "metadata": {
            "gender": "female" if index % 2 else "male",
            "age": "twenties",
            "sentence_domain": "general",
            "vote_margin_bin": "four_plus",
        },
        "license": {
            "spdx": "CC0-1.0",
            "policy": "strict",
            "attribution_key": record.dataset_id,
        },
        "qc": {"hard_pass": True, "flags": []},
    }


def make_prepared_fixture(tmp_path: Path, count: int = 6):
    record = fixture_record(count)
    prepared = tmp_path / "data/prepared" / record.dataset_id / record.version
    rows = []
    for index in range(count):
        duration = 2 * 16000
        timeline = np.arange(duration)
        pcm = (3000 * np.sin(2 * np.pi * (220 + index * 20) * timeline / 16000)).astype(np.int16)
        pcm[:1600] = 0
        pcm[-1600:] = 0
        if index == 0:
            pcm[: 16000 + 3200] = 0
        reference = "同じ文章です。" if index in (1, 2) else f"品質確認用の文章{index}です。"
        rows.append(fixture_row(record, prepared, index, pcm, reference))
    write_jsonl_atomic(prepared / "manifest.jsonl", rows)
    return record, rows


def test_qc_builds_official_and_clean_without_changing_raw_reference(tmp_path):
    record, source_rows = make_prepared_fixture(tmp_path)
    report, report_dir = run_qc(record, tmp_path / "data", tmp_path / "artifacts")
    official_path = tmp_path / "data" / report["views"]["official"]["manifest_relative_to_data_root"]
    clean_path = tmp_path / "data" / report["views"]["clean"]["manifest_relative_to_data_root"]
    stress_path = tmp_path / "data" / report["views"]["stress"]["manifest_relative_to_data_root"]
    official = load_manifest(official_path)
    clean = load_manifest(clean_path)
    stress = load_manifest(stress_path)
    assert clean
    assert [row["reference_raw"] for row in official] == [
        row["reference_raw"] for row in source_rows
    ]
    source_reference = {row["sample_id"]: row["reference_raw"] for row in source_rows}
    assert all(row["reference_raw"] == source_reference[row["sample_id"]]
               for row in clean + stress)
    assert report["views"]["official"]["rows"] == 6
    assert report["views"]["clean"]["rows"] < 6
    assert report["views"]["clean"]["rows"] + report["views"]["stress"]["rows"] == 6
    assert {row["sample_id"] for row in clean}.isdisjoint(
        row["sample_id"] for row in stress)
    assert all(not row["qc"]["flags"] for row in clean)
    assert all(row["qc"]["flags"] for row in stress)
    assert "long_leading_silence" in official[0]["qc"]["flags"]
    assert report["duplicates"]["raw_text"]["groups"] == 1
    assert not report["hard_failures"]
    assert (report_dir / "qc.json").is_file()
    assert "Official retains every evaluable row" in (report_dir / "qc.html").read_text()
    assert "No ASR hypothesis" in (report_dir / "qc.md").read_text()


def test_qc_reports_missing_audio_as_hard_failure(tmp_path):
    record, rows = make_prepared_fixture(tmp_path, count=2)
    prepared = tmp_path / "data/prepared" / record.dataset_id / record.version
    (prepared / rows[0]["audio_path"]).unlink()
    report, _ = run_qc(record, tmp_path / "data", tmp_path / "artifacts")
    assert len(report["hard_failures"]) == 1
    assert report["views"]["official"]["rows"] == 1


def test_qc_rejects_unsafe_audio_path_without_reading_outside_root(tmp_path):
    record, rows = make_prepared_fixture(tmp_path, count=1)
    prepared = tmp_path / "data/prepared" / record.dataset_id / record.version
    rows[0]["audio_path"] = "../../outside.flac"
    write_jsonl_atomic(prepared / "manifest.jsonl", rows)
    report, _ = run_qc(record, tmp_path / "data", tmp_path / "artifacts")
    assert report["hard_failures"][0]["error"] == "unsafe audio path"


def test_qc_rejects_windows_style_audio_path_on_every_platform(tmp_path):
    record, rows = make_prepared_fixture(tmp_path, count=1)
    prepared = tmp_path / "data/prepared" / record.dataset_id / record.version
    rows[0]["audio_path"] = "audio\\outside.flac"
    write_jsonl_atomic(prepared / "manifest.jsonl", rows)
    report, _ = run_qc(record, tmp_path / "data", tmp_path / "artifacts")
    assert report["hard_failures"][0]["error"] == "unsafe audio path"


def test_qc_flags_same_pcm_without_removing_it_from_official(tmp_path):
    record, rows = make_prepared_fixture(tmp_path, count=2)
    prepared = tmp_path / "data/prepared" / record.dataset_id / record.version
    rows[1]["audio_path"] = rows[0]["audio_path"]
    rows[1]["audio_sha256"] = rows[0]["audio_sha256"]
    rows[1]["pcm_sha256"] = rows[0]["pcm_sha256"]
    rows[1]["duration_s"] = rows[0]["duration_s"]
    write_jsonl_atomic(prepared / "manifest.jsonl", rows)
    report, _ = run_qc(record, tmp_path / "data", tmp_path / "artifacts")
    assert report["duplicates"]["prepared_pcm"] == {"groups": 1, "affected_rows": 2}
    assert report["views"]["official"]["rows"] == 2
    assert report["views"]["clean"]["rows"] == 0


def test_qc_rejects_row_from_another_split(tmp_path):
    record, rows = make_prepared_fixture(tmp_path, count=1)
    prepared = tmp_path / "data/prepared" / record.dataset_id / record.version
    rows[0]["source_split"] = "dev"
    write_jsonl_atomic(prepared / "manifest.jsonl", rows)
    report, _ = run_qc(record, tmp_path / "data", tmp_path / "artifacts")
    assert report["hard_failures"][0]["error"] == "unexpected source split in prepared manifest"


def test_qc_rejects_changed_prepared_audio_hash(tmp_path):
    record, rows = make_prepared_fixture(tmp_path, count=1)
    prepared = tmp_path / "data/prepared" / record.dataset_id / record.version
    rows[0]["audio_sha256"] = "0" * 64
    write_jsonl_atomic(prepared / "manifest.jsonl", rows)
    report, _ = run_qc(record, tmp_path / "data", tmp_path / "artifacts")
    assert report["hard_failures"][0]["error"] == "prepared audio hash changed"
