from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys

import huggingface_hub
from huggingface_hub import hf_hub_download

from ..config import load_yaml_mapping
from ..errors import DatasetPreparationError
from ..hashing import sha256_file, stable_sample_id
from ..licensing.policy import check_dataset_license
from ..licensing.registry import DatasetRecord
from ..paths import CONFIG_DIR
from ..prepare.archives import extract_tar_safely
from ..prepare.audio import convert_to_standard_flac, ffmpeg_version, inspect_prepared_audio
from ..prepare.manifest import load_manifest, write_json_atomic, write_jsonl_atomic
from ..prepare.text import (
    has_forbidden_control,
    normalize_reference_nfc,
    normalize_reference_standard,
    text_qc_flags,
)
from ..schema_validation import validate_schema
from .base import PreparedDataset


ADAPTER_VERSION = 1
NORMALIZATION_VERSION = 1
TSV_REPO_PATH = "data/ja_jp/test.tsv"
AUDIO_REPO_PATH = "data/ja_jp/audio/test.tar.gz"


def _dataset_paths(data_root: Path, record: DatasetRecord) -> dict[str, Path]:
    base = data_root / "downloads" / record.dataset_id / record.version
    return {
        "download": base,
        "tsv": base / "test.tsv",
        "archive": base / "test.tar.gz",
        "receipt": base / "download.receipt.json",
        "raw": data_root / "raw" / record.dataset_id / record.version,
        "prepared": data_root / "prepared" / record.dataset_id / record.version,
    }


def _copy_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256_file(source) != sha256_file(destination):
            raise DatasetPreparationError(f"refusing to overwrite changed download: {destination.name}")
        return
    part = destination.with_name(destination.name + ".part")
    try:
        if part.exists():
            part.unlink()
        with source.open("rb") as src, part.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        os.replace(part, destination)
    finally:
        if part.exists():
            part.unlink()


def download_fleurs(record: DatasetRecord, data_root: str | Path) -> dict:
    check_dataset_license(record)
    if record.dataset_id != "fleurs_ja":
        raise DatasetPreparationError("FLEURS adapter received another dataset")
    revision = record.raw.get("source_revision")
    if not revision or record.raw.get("source_repo") != "google/fleurs":
        raise DatasetPreparationError("FLEURS registry must pin repo and revision")
    paths = _dataset_paths(Path(data_root), record)
    downloaded = {}
    for repo_path, target_key in ((TSV_REPO_PATH, "tsv"), (AUDIO_REPO_PATH, "archive")):
        try:
            cached = Path(hf_hub_download(
                repo_id="google/fleurs",
                filename=repo_path,
                repo_type="dataset",
                revision=revision,
            ))
        except Exception as exc:
            # Hub failures may contain signed URLs or credential context.
            # Keep the CLI error deliberately generic.
            raise DatasetPreparationError(
                f"FLEURS download failed for registered file {repo_path!r}") from exc
        _copy_atomic(cached, paths[target_key])
        downloaded[repo_path] = {
            "filename": paths[target_key].name,
            "sha256": sha256_file(paths[target_key]),
            "size": paths[target_key].stat().st_size,
        }
    receipt = {
        "schema_version": 1,
        "dataset_id": record.dataset_id,
        "source_repo": "google/fleurs",
        "source_revision": revision,
        "source_config": record.raw["source_config"],
        "source_split": record.source_split,
        "files": downloaded,
    }
    write_json_atomic(paths["receipt"], receipt)
    return receipt


def _read_tsv(path: Path, expected_rows: int) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for line_number, values in enumerate(reader, start=1):
            if len(values) != 7:
                raise DatasetPreparationError(
                    f"FLEURS test.tsv row {line_number} has {len(values)} columns, expected 7")
            sentence_id, filename, raw_transcription, transcription, char_tokens, num_samples, gender = values
            if not sentence_id or not filename or Path(filename).name != filename:
                raise DatasetPreparationError(f"invalid FLEURS identity at row {line_number}")
            try:
                sample_count = int(num_samples)
            except ValueError as exc:
                raise DatasetPreparationError(
                    f"invalid FLEURS num_samples at row {line_number}") from exc
            rows.append({
                "sentence_id": sentence_id,
                "filename": filename,
                "raw_transcription": raw_transcription,
                "transcription": transcription,
                "char_tokens": char_tokens,
                "num_samples": sample_count,
                "gender": gender.casefold(),
            })
    if len(rows) != expected_rows:
        raise DatasetPreparationError(
            f"FLEURS row count changed: expected {expected_rows}, got {len(rows)}")
    filenames = [row["filename"] for row in rows]
    if len(filenames) != len(set(filenames)):
        raise DatasetPreparationError("FLEURS test.tsv contains duplicate audio filenames")
    return rows


def _duration_bin(duration_s: float) -> str:
    if duration_s < 3:
        return "short"
    if duration_s <= 8:
        return "medium"
    return "long"


def prepare_fleurs(record: DatasetRecord, data_root: str | Path) -> PreparedDataset:
    check_dataset_license(record)
    paths = _dataset_paths(Path(data_root), record)
    if not paths["tsv"].is_file() or not paths["archive"].is_file():
        raise DatasetPreparationError("FLEURS download is missing; run dataset download fleurs_ja")
    try:
        receipt = json.loads(paths["receipt"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetPreparationError(
            "FLEURS download receipt is missing or invalid; run dataset download fleurs_ja") from exc
    if receipt.get("source_revision") != record.raw.get("source_revision"):
        raise DatasetPreparationError("FLEURS download revision does not match registry")
    if receipt["files"][TSV_REPO_PATH]["sha256"] != sha256_file(paths["tsv"]):
        raise DatasetPreparationError("downloaded FLEURS test.tsv hash changed")
    if receipt["files"][AUDIO_REPO_PATH]["sha256"] != sha256_file(paths["archive"]):
        raise DatasetPreparationError("downloaded FLEURS audio archive hash changed")

    expected_rows = record.expected.get("rows")
    if not isinstance(expected_rows, int) or expected_rows <= 0:
        raise DatasetPreparationError("FLEURS registry must declare a positive expected row count")
    source_rows = _read_tsv(paths["tsv"], expected_rows)
    extracted = extract_tar_safely(paths["archive"], paths["raw"])
    wav_by_name: dict[str, Path] = {}
    member_by_name: dict[str, str] = {}
    for path in extracted:
        if path.suffix.casefold() != ".wav":
            continue
        if path.name in wav_by_name:
            raise DatasetPreparationError(f"duplicate FLEURS archive filename: {path.name}")
        wav_by_name[path.name] = path
        member_by_name[path.name] = path.relative_to(paths["raw"]).as_posix()
    missing = [row["filename"] for row in source_rows if row["filename"] not in wav_by_name]
    if missing:
        raise DatasetPreparationError(
            f"FLEURS archive is missing {len(missing)} test files; first: {missing[0]}")
    expected_filenames = {row["filename"] for row in source_rows}
    unexpected = sorted(set(wav_by_name) - expected_filenames)
    if unexpected:
        raise DatasetPreparationError(
            f"FLEURS test archive has unexpected audio files; first: {unexpected[0]}")

    thresholds = load_yaml_mapping(CONFIG_DIR / "qc_thresholds.yaml")
    audio_thresholds = thresholds["audio"]
    text_thresholds = thresholds["text"]
    manifest_rows = []
    pcm_to_rows: dict[str, list[int]] = defaultdict(list)
    failures = []
    for source in source_rows:
        raw_reference = source["raw_transcription"]
        if not raw_reference.strip() or has_forbidden_control(raw_reference):
            failures.append(f"{source['filename']}: empty or invalid reference")
            continue
        source_sample_id = Path(source["filename"]).stem
        sample_id = stable_sample_id(
            record.dataset_id, record.version, record.source_split, source_sample_id)
        output = paths["prepared"] / "audio" / sample_id[:2] / f"{sample_id}.flac"
        try:
            convert_to_standard_flac(wav_by_name[source["filename"]], output)
            audio = inspect_prepared_audio(output, audio_thresholds)
        except DatasetPreparationError as exc:
            failures.append(f"{source['filename']}: {exc}")
            continue
        reference_nfc = normalize_reference_nfc(raw_reference)
        # FLEURS defines `transcription` as the ASR reference while
        # `raw_transcription` retains the source presentation. Keep both.
        reference_eval = normalize_reference_standard(source["transcription"])
        if not reference_eval:
            failures.append(f"{source['filename']}: normalized reference is empty")
            continue
        flags = list(audio.flags)
        flags.extend(text_qc_flags(
            raw_reference, reference_eval,
            short_chars=text_thresholds["very_short_chars"],
            long_chars=text_thresholds["very_long_chars"],
            digit_heavy_ratio=text_thresholds["digit_heavy_ratio"],
        ))
        if round(audio.duration_s * audio.sample_rate) != source["num_samples"]:
            failures.append(f"{source['filename']}: source sample count does not match decoded audio")
            continue
        row = {
            "schema_version": 1,
            "sample_id": sample_id,
            "dataset_id": record.dataset_id,
            "dataset_version": record.version,
            "source_split": record.source_split,
            "source_sample_id": source_sample_id,
            "audio_path": output.relative_to(paths["prepared"]).as_posix(),
            "source_audio_path": member_by_name[source["filename"]],
            "source_audio_sha256": sha256_file(wav_by_name[source["filename"]]),
            "audio_sha256": sha256_file(output),
            "pcm_sha256": audio.pcm_sha256,
            "sample_rate": audio.sample_rate,
            "channels": audio.channels,
            "duration_s": audio.duration_s,
            "reference_raw": raw_reference,
            "reference_nfc": reference_nfc,
            "reference_eval": reference_eval,
            "speaker_id": None,
            "categories": ["read", "fleurs", _duration_bin(audio.duration_s)],
            "metadata": {
                "fleurs_sentence_id": source["sentence_id"],
                "gender": source["gender"],
                "source_transcription": source["transcription"],
                "source_num_samples": source["num_samples"],
            },
            "license": {
                "spdx": record.license.spdx,
                "policy": record.license.policy,
                "attribution_key": record.dataset_id,
            },
            "qc": {
                **audio.qc_dict(),
                "flags": sorted(set(flags)),
            },
        }
        pcm_to_rows[audio.pcm_sha256].append(len(manifest_rows))
        manifest_rows.append(row)
    if failures:
        preview = "; ".join(failures[:3])
        raise DatasetPreparationError(
            f"FLEURS preparation had {len(failures)} hard failures: {preview}")
    for indexes in pcm_to_rows.values():
        if len(indexes) > 1:
            for index in indexes:
                manifest_rows[index]["qc"]["flags"] = sorted(set(
                    manifest_rows[index]["qc"]["flags"] + ["duplicate_pcm"]))
    for row in manifest_rows:
        validate_schema(row, "manifest.schema.json")

    manifest_path = paths["prepared"] / "manifest.jsonl"
    row_count, manifest_hash = write_jsonl_atomic(manifest_path, manifest_rows)
    flag_counts = Counter(
        flag for row in manifest_rows for flag in row["qc"]["flags"])
    qc_summary = {
        "schema_version": 1,
        "dataset_id": record.dataset_id,
        "view": "official",
        "row_count": row_count,
        "hard_failures": 0,
        "flag_counts": dict(sorted(flag_counts.items())),
    }
    qc_summary_path = paths["prepared"] / "qc-summary.json"
    write_json_atomic(qc_summary_path, qc_summary)
    lock = {
        "schema_version": 1,
        "dataset_id": record.dataset_id,
        "version": record.version,
        "source_revision": record.raw["source_revision"],
        "source_split": record.source_split,
        "source_config": record.raw["source_config"],
        "license_spdx": record.license.spdx,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "adapter_version": ADAPTER_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "row_count": row_count,
        "source_manifest_sha256": sha256_file(paths["tsv"]),
        "prepared_manifest_sha256": manifest_hash,
        "tool_versions": {
            "python": sys.version.split()[0],
            "ffmpeg": ffmpeg_version(),
            "huggingface_hub": huggingface_hub.__version__,
        },
    }
    validate_schema(lock, "dataset_lock.schema.json")
    lock_path = paths["prepared"] / "dataset.lock.json"
    write_json_atomic(lock_path, lock)
    return PreparedDataset(
        dataset_id=record.dataset_id,
        manifest_path=manifest_path,
        lock_path=lock_path,
        row_count=row_count,
        manifest_sha256=manifest_hash,
        qc_summary_path=qc_summary_path,
    )


def verify_prepared_fleurs(record: DatasetRecord, data_root: str | Path) -> PreparedDataset:
    paths = _dataset_paths(Path(data_root), record)
    lock_path = paths["prepared"] / "dataset.lock.json"
    manifest_path = paths["prepared"] / "manifest.jsonl"
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetPreparationError("prepared FLEURS lock is missing or invalid") from exc
    rows = load_manifest(manifest_path)
    expected = record.expected["rows"]
    if len(rows) != expected or lock.get("row_count") != expected:
        raise DatasetPreparationError("prepared FLEURS row count does not match registry")
    manifest_hash = sha256_file(manifest_path)
    if lock.get("prepared_manifest_sha256") != manifest_hash:
        raise DatasetPreparationError("prepared FLEURS manifest hash does not match lock")
    if lock.get("source_revision") != record.raw["source_revision"]:
        raise DatasetPreparationError("prepared FLEURS revision does not match registry")
    missing = [row["sample_id"] for row in rows
               if not (paths["prepared"] / row["audio_path"]).is_file()]
    if missing:
        raise DatasetPreparationError(f"prepared FLEURS audio is missing: {missing[0]}")
    return PreparedDataset(
        dataset_id=record.dataset_id,
        manifest_path=manifest_path,
        lock_path=lock_path,
        row_count=len(rows),
        manifest_sha256=manifest_hash,
        qc_summary_path=paths["prepared"] / "qc-summary.json",
    )
