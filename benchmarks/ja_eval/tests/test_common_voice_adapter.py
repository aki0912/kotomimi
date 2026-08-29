from dataclasses import replace
import io
import json
from pathlib import Path
import shutil
import struct
import sys
import tarfile
from types import SimpleNamespace
import wave

import pytest

from kotomimi_eval.datasets.common_voice import (
    _read_test_tsv,
    download_common_voice,
    import_common_voice_archive,
    prepare_common_voice,
    verify_prepared_common_voice,
)
from kotomimi_eval.errors import DatasetPreparationError
from kotomimi_eval.licensing.registry import load_registry
from kotomimi_eval.prepare.manifest import load_manifest


HEADER = (
    "client_id\tpath\tsentence_id\tsentence\tsentence_domain\tup_votes\t"
    "down_votes\tage\tgender\taccents\tvariant\tlocale\tsegment\n"
)


def _wav_bytes(frequency: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        samples = [
            int(4000 * ((index * frequency // 16000) % 2 * 2 - 1))
            for index in range(16000)
        ]
        handle.writeframes(b"".join(struct.pack("<h", value) for value in samples))
    return output.getvalue()


def _record(row_count: int = 3):
    base = load_registry().get("common_voice_ja_26")
    return replace(base, expected={"rows": row_count})


def _archive(path: Path, *, include_third_clip: bool = True) -> Path:
    rows = (
        "raw-client-a\tone.mp3\ts1\tＡＩは、便利です。\tgeneral\t4\t0\ttwenties\tfemale\t\t\tja\t\n"
        "raw-client-a\ttwo.mp3\ts2\t今日は東京です。\tnews\t2\t1\ttwenties\tfemale\t\t\tja\t\n"
        "raw-client-b\tthree.mp3\ts3\t価格は123円です。\tgeneral\t1\t1\tthirties\tmale\t\t\tja\t\n"
    )
    with tarfile.open(path, "w:gz") as handle:
        for name, content in (
            ("cv-corpus-26.0-2026-06-12/ja/test.tsv", (HEADER + rows).encode()),
            ("cv-corpus-26.0-2026-06-12/ja/dev.tsv", (HEADER + rows[:rows.find("\n") + 1]).encode()),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            handle.addfile(info, io.BytesIO(content))
        clips = [("one.mp3", 220), ("two.mp3", 330)]
        if include_third_clip:
            clips.append(("three.mp3", 440))
        for filename, frequency in clips:
            content = _wav_bytes(frequency)
            info = tarfile.TarInfo(f"cv-corpus-26.0-2026-06-12/ja/clips/{filename}")
            info.size = len(content)
            handle.addfile(info, io.BytesIO(content))
    return path


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_common_voice_fixture_preserves_raw_and_hides_client_id(tmp_path):
    record = _record()
    source = _archive(tmp_path / "common-voice.tar.gz")
    receipt = import_common_voice_archive(record, tmp_path / "data", source)
    assert receipt["redistribution_allowed"] is False

    first = prepare_common_voice(record, tmp_path / "data")
    rows = load_manifest(first.manifest_path)
    manifest_text = first.manifest_path.read_text(encoding="utf-8")
    assert first.row_count == 3
    assert {row["source_split"] for row in rows} == {"test"}
    assert rows[0]["reference_raw"] == "ＡＩは、便利です。"
    assert rows[0]["reference_nfc"] == "ＡＩは、便利です。"
    assert rows[0]["reference_eval"] == "aiは便利です"
    assert rows[0]["metadata"]["vote_margin"] == 4
    assert rows[0]["metadata"]["sentence_domain"] == "general"
    assert rows[0]["speaker_id"] == rows[1]["speaker_id"]
    assert rows[0]["speaker_id"] != rows[2]["speaker_id"]
    assert "raw-client-a" not in manifest_text
    assert "raw-client-b" not in manifest_text
    assert "client_id" not in manifest_text
    assert (tmp_path / "data/cache/common_voice_ja_26/speaker-id.salt").is_file()

    second = prepare_common_voice(record, tmp_path / "data")
    assert second.manifest_sha256 == first.manifest_sha256
    assert verify_prepared_common_voice(record, tmp_path / "data").row_count == 3


def test_common_voice_requires_exact_row_count(tmp_path):
    tsv = tmp_path / "test.tsv"
    tsv.write_text(
        HEADER
        + "client\tone.mp3\ts1\t正解です。\tgeneral\t2\t0\t\t\t\t\tja\t\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetPreparationError, match="row count changed"):
        _read_test_tsv(tsv, expected_rows=2)


def test_common_voice_rejects_unsafe_clip_path(tmp_path):
    tsv = tmp_path / "test.tsv"
    tsv.write_text(
        HEADER
        + "client\t../one.mp3\ts1\t正解です。\tgeneral\t2\t0\t\t\t\t\tja\t\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetPreparationError, match="invalid clip path"):
        _read_test_tsv(tsv, expected_rows=1)


def test_common_voice_rejects_unregistered_release_root(tmp_path):
    record = _record()
    source = _archive(tmp_path / "wrong-release.tar.gz")
    rewritten = tmp_path / "rewritten.tar.gz"
    with tarfile.open(source, "r:gz") as original, tarfile.open(rewritten, "w:gz") as target:
        for member in original.getmembers():
            payload = original.extractfile(member) if member.isfile() else None
            member.name = member.name.replace("cv-corpus-26.0-2026-06-12", "cv-corpus-25.0")
            target.addfile(member, payload)
    import_common_voice_archive(record, tmp_path / "data", rewritten)
    with pytest.raises(DatasetPreparationError, match="registered cv-corpus-26.0"):
        prepare_common_voice(record, tmp_path / "data")


def test_common_voice_missing_test_clip_is_hard_failure(tmp_path):
    record = _record()
    source = _archive(tmp_path / "missing.tar.gz", include_third_clip=False)
    import_common_voice_archive(record, tmp_path / "data", source)
    with pytest.raises(DatasetPreparationError, match="missing 1 test clips"):
        prepare_common_voice(record, tmp_path / "data")


def test_common_voice_import_refuses_different_archive(tmp_path):
    record = _record()
    first = _archive(tmp_path / "first.tar.gz")
    second = tmp_path / "second.tar.gz"
    second.write_bytes(b"not the same archive")
    import_common_voice_archive(record, tmp_path / "data", first)
    with pytest.raises(DatasetPreparationError, match="refusing to overwrite"):
        import_common_voice_archive(record, tmp_path / "data", second)


def test_common_voice_receipt_contains_no_source_location(tmp_path):
    record = _record()
    source = _archive(tmp_path / "private-location.tar.gz")
    receipt = import_common_voice_archive(record, tmp_path / "data", source)
    serialized = json.dumps(receipt)
    assert "private-location" not in serialized


def test_common_voice_optional_downloader_uses_registered_dataset_id(tmp_path, monkeypatch):
    record = _record()
    source = _archive(tmp_path / "sdk-download.tar.gz")
    calls = []

    def fake_download(dataset_id, **kwargs):
        calls.append((dataset_id, kwargs))
        return source

    monkeypatch.setitem(
        sys.modules, "datacollective", SimpleNamespace(download_dataset=fake_download))
    receipt = download_common_voice(record, tmp_path / "data")
    assert calls[0][0] == "cmqim4lxy00tunr07cjkcupeg"
    assert calls[0][1]["overwrite_existing"] is False
    assert calls[0][1]["show_progress"] is True
    assert receipt["version"] == "26.0"
