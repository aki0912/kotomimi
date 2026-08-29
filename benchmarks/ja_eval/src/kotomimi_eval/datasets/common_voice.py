from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import secrets
import shutil
import sys

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
REQUIRED_COLUMNS = frozenset({
    "client_id", "path", "sentence", "up_votes", "down_votes", "age", "gender",
})


def _dataset_paths(data_root: Path, record: DatasetRecord) -> dict[str, Path]:
    download = data_root / "downloads" / record.dataset_id / record.version
    archive_name = record.raw.get("expected_archive_name")
    if not isinstance(archive_name, str) or Path(archive_name).name != archive_name:
        raise DatasetPreparationError("Common Voice registry has an invalid archive name")
    return {
        "download": download,
        "archive": download / archive_name,
        "receipt": download / "archive.receipt.json",
        "raw": data_root / "raw" / record.dataset_id / record.version,
        "prepared": data_root / "prepared" / record.dataset_id / record.version,
        "salt": data_root / "cache" / record.dataset_id / "speaker-id.salt",
    }


def _copy_atomic(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise DatasetPreparationError("Common Voice archive does not exist or is not a file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_hash = sha256_file(source)
    if destination.exists():
        if source.resolve() == destination.resolve() or source_hash == sha256_file(destination):
            return
        raise DatasetPreparationError("refusing to overwrite a different Common Voice archive")
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


def import_common_voice_archive(
    record: DatasetRecord, data_root: str | Path, archive: str | Path,
) -> dict:
    check_dataset_license(record)
    if record.dataset_id != "common_voice_ja_26":
        raise DatasetPreparationError("Common Voice adapter received another dataset")
    paths = _dataset_paths(Path(data_root), record)
    source = Path(archive).expanduser()
    _copy_atomic(source, paths["archive"])
    receipt = {
        "schema_version": 1,
        "dataset_id": record.dataset_id,
        "version": record.version,
        "source_release": record.raw.get("source_release"),
        "source_dataset_id": record.raw.get("source_dataset_id"),
        "source_split": record.source_split,
        "archive": {
            "filename": paths["archive"].name,
            "sha256": sha256_file(paths["archive"]),
            "size": paths["archive"].stat().st_size,
        },
        "redistribution_allowed": False,
    }
    write_json_atomic(paths["receipt"], receipt)
    return receipt


def download_common_voice(record: DatasetRecord, data_root: str | Path) -> dict:
    check_dataset_license(record)
    dataset_id = record.raw.get("source_dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id:
        raise DatasetPreparationError("Common Voice registry must declare source_dataset_id")
    try:
        from datacollective import download_dataset
    except ImportError as exc:
        raise DatasetPreparationError(
            "Common Voice API download requires the optional 'mdc' dependency; "
            "install kotomimi-ja-eval[mdc] or use dataset import") from exc
    paths = _dataset_paths(Path(data_root), record)
    paths["download"].mkdir(parents=True, exist_ok=True)
    try:
        downloaded = Path(download_dataset(
            dataset_id,
            download_directory=str(paths["download"]),
            show_progress=True,
            overwrite_existing=False,
        ))
    except Exception as exc:
        # SDK failures can contain API credentials or signed download URLs.
        raise DatasetPreparationError(
            "Common Voice API download failed; verify MDC access and credentials") from exc
    return import_common_voice_archive(record, data_root, downloaded)


def _find_japanese_test_tsv(
    extracted: list[Path], raw_root: Path, locale: str, source_release: str,
) -> Path:
    candidates = [
        path for path in extracted
        if (path.name == "test.tsv" and path.parent.name == locale
            and path.parent.parent.name == source_release)
    ]
    if len(candidates) != 1:
        relative = [path.relative_to(raw_root).as_posix() for path in candidates]
        raise DatasetPreparationError(
            "Common Voice archive must contain exactly one registered "
            f"{source_release}/{locale}/test.tsv; found {relative}")
    return candidates[0]


def _read_test_tsv(path: Path, expected_rows: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            fields = set(reader.fieldnames or [])
            missing_columns = sorted(REQUIRED_COLUMNS - fields)
            if missing_columns:
                raise DatasetPreparationError(
                    f"Common Voice test.tsv is missing columns: {', '.join(missing_columns)}")
            for line_number, row in enumerate(reader, start=2):
                if None in row:
                    raise DatasetPreparationError(
                        f"Common Voice test.tsv row {line_number} has extra columns")
                clip = row.get("path", "")
                if not clip or "/" in clip or "\\" in clip or Path(clip).name != clip:
                    raise DatasetPreparationError(
                        f"Common Voice test.tsv row {line_number} has an invalid clip path")
                if not row.get("client_id"):
                    raise DatasetPreparationError(
                        f"Common Voice test.tsv row {line_number} has no client_id")
                for field in ("up_votes", "down_votes"):
                    try:
                        int(row.get(field, ""))
                    except (TypeError, ValueError) as exc:
                        raise DatasetPreparationError(
                            f"Common Voice test.tsv row {line_number} has invalid {field}") from exc
                rows.append({key: value or "" for key, value in row.items()})
    except UnicodeDecodeError as exc:
        raise DatasetPreparationError("Common Voice test.tsv is not valid UTF-8") from exc
    if len(rows) != expected_rows:
        raise DatasetPreparationError(
            f"Common Voice row count changed: expected {expected_rows}, got {len(rows)}")
    clips = [row["path"] for row in rows]
    if len(clips) != len(set(clips)):
        raise DatasetPreparationError("Common Voice test.tsv contains duplicate clip paths")
    return rows


def _load_or_create_salt(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        salt = path.read_bytes()
    except FileNotFoundError:
        salt = secrets.token_bytes(32)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            salt = path.read_bytes()
        else:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(salt)
    if len(salt) != 32:
        raise DatasetPreparationError("Common Voice local speaker salt is invalid")
    return salt


def _speaker_id(dataset_id: str, salt: bytes, client_id: str) -> str:
    digest = hashlib.sha256()
    digest.update(dataset_id.encode("utf-8"))
    digest.update(b"\0")
    digest.update(salt)
    digest.update(b"\0")
    digest.update(client_id.encode("utf-8"))
    return digest.hexdigest()


def _duration_bin(duration_s: float) -> str:
    if duration_s < 3:
        return "short"
    if duration_s <= 8:
        return "medium"
    return "long"


def _vote_margin_bin(margin: int) -> str:
    if margin <= 0:
        return "nonpositive"
    if margin == 1:
        return "one"
    if margin <= 3:
        return "two_to_three"
    return "four_plus"


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def prepare_common_voice(record: DatasetRecord, data_root: str | Path) -> PreparedDataset:
    check_dataset_license(record)
    paths = _dataset_paths(Path(data_root), record)
    if not paths["archive"].is_file() or not paths["receipt"].is_file():
        raise DatasetPreparationError(
            "Common Voice archive is missing; run dataset import or authenticated dataset download")
    try:
        receipt = json.loads(paths["receipt"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetPreparationError("Common Voice archive receipt is missing or invalid") from exc
    if (receipt.get("version") != record.version
            or receipt.get("source_release") != record.raw.get("source_release")
            or receipt.get("source_dataset_id") != record.raw.get("source_dataset_id")):
        raise DatasetPreparationError("Common Voice archive receipt does not match registry")
    archive_info = receipt.get("archive", {})
    if archive_info.get("sha256") != sha256_file(paths["archive"]):
        raise DatasetPreparationError("Common Voice archive hash changed after import")

    expected_rows = record.expected.get("rows")
    if not isinstance(expected_rows, int) or expected_rows <= 0:
        raise DatasetPreparationError("Common Voice registry must declare expected rows")
    locale = record.raw.get("source_locale", "ja")
    source_release = record.raw.get("source_release")
    if (not isinstance(locale, str) or not locale
            or not isinstance(source_release, str) or not source_release):
        raise DatasetPreparationError(
            "Common Voice registry must declare source locale and release")
    extracted = extract_tar_safely(
        paths["archive"], paths["raw"], max_total_bytes=50 * 1024**3, max_members=250_000)
    test_tsv = _find_japanese_test_tsv(
        extracted, paths["raw"], locale, source_release)
    source_rows = _read_test_tsv(test_tsv, expected_rows)
    clips_dir = test_tsv.parent / "clips"
    missing = [row["path"] for row in source_rows if not (clips_dir / row["path"]).is_file()]
    if missing:
        raise DatasetPreparationError(
            f"Common Voice archive is missing {len(missing)} test clips; first: {missing[0]}")

    thresholds = load_yaml_mapping(CONFIG_DIR / "qc_thresholds.yaml")
    audio_thresholds = thresholds["audio"]
    text_thresholds = thresholds["text"]
    salt = _load_or_create_salt(paths["salt"])
    manifest_rows = []
    pcm_to_rows: dict[str, list[int]] = defaultdict(list)
    failures = []
    for source in source_rows:
        raw_reference = source["sentence"]
        if not raw_reference.strip() or has_forbidden_control(raw_reference):
            failures.append(f"{source['path']}: empty or invalid reference")
            continue
        source_sample_id = source["path"]
        sample_id = stable_sample_id(
            record.dataset_id, record.version, record.source_split, source_sample_id)
        source_audio = clips_dir / source["path"]
        output = paths["prepared"] / "audio" / sample_id[:2] / f"{sample_id}.flac"
        try:
            convert_to_standard_flac(source_audio, output)
            audio = inspect_prepared_audio(output, audio_thresholds)
        except DatasetPreparationError as exc:
            failures.append(f"{source['path']}: {exc}")
            continue
        reference_nfc = normalize_reference_nfc(raw_reference)
        reference_eval = normalize_reference_standard(raw_reference)
        if not reference_eval:
            failures.append(f"{source['path']}: normalized reference is empty")
            continue
        up_votes = int(source["up_votes"])
        down_votes = int(source["down_votes"])
        vote_margin = up_votes - down_votes
        domain = source.get("sentence_domain", "").strip() or "unknown"
        age = source.get("age", "").strip().casefold() or "unknown"
        gender = source.get("gender", "").strip().casefold() or "unknown"
        flags = list(audio.flags)
        flags.extend(text_qc_flags(
            raw_reference, reference_eval,
            short_chars=text_thresholds["very_short_chars"],
            long_chars=text_thresholds["very_long_chars"],
            digit_heavy_ratio=text_thresholds["digit_heavy_ratio"],
        ))
        relative_source = source_audio.relative_to(paths["raw"]).as_posix()
        row = {
            "schema_version": 1,
            "sample_id": sample_id,
            "dataset_id": record.dataset_id,
            "dataset_version": record.version,
            "source_split": record.source_split,
            "source_sample_id": source_sample_id,
            "audio_path": output.relative_to(paths["prepared"]).as_posix(),
            "source_audio_path": relative_source,
            "source_audio_sha256": sha256_file(source_audio),
            "audio_sha256": sha256_file(output),
            "pcm_sha256": audio.pcm_sha256,
            "sample_rate": audio.sample_rate,
            "channels": audio.channels,
            "duration_s": audio.duration_s,
            "reference_raw": raw_reference,
            "reference_nfc": reference_nfc,
            "reference_eval": reference_eval,
            "speaker_id": _speaker_id(record.dataset_id, salt, source["client_id"]),
            "categories": sorted(set(["read", "common_voice", _duration_bin(audio.duration_s), domain])),
            "metadata": {
                "sentence_id": source.get("sentence_id", ""),
                "sentence_domain": domain,
                "up_votes": up_votes,
                "down_votes": down_votes,
                "vote_margin": vote_margin,
                "vote_margin_bin": _vote_margin_bin(vote_margin),
                "age": age,
                "gender": gender,
                "accents": source.get("accents", ""),
                "variant": source.get("variant", ""),
                "locale": source.get("locale", "") or locale,
                "segment": source.get("segment", ""),
            },
            "license": {
                "spdx": record.license.spdx,
                "policy": record.license.policy,
                "attribution_key": record.dataset_id,
            },
            "qc": {**audio.qc_dict(), "flags": sorted(set(flags))},
        }
        pcm_to_rows[audio.pcm_sha256].append(len(manifest_rows))
        manifest_rows.append(row)
    if failures:
        raise DatasetPreparationError(
            f"Common Voice preparation had {len(failures)} hard failures: {'; '.join(failures[:3])}")
    for indexes in pcm_to_rows.values():
        if len(indexes) > 1:
            for index in indexes:
                flags = manifest_rows[index]["qc"]["flags"]
                manifest_rows[index]["qc"]["flags"] = sorted(set(flags + ["duplicate_pcm"]))
    for row in manifest_rows:
        validate_schema(row, "manifest.schema.json")

    manifest_path = paths["prepared"] / "manifest.jsonl"
    row_count, manifest_hash = write_jsonl_atomic(manifest_path, manifest_rows)
    flag_counts = Counter(flag for row in manifest_rows for flag in row["qc"]["flags"])
    qc_summary_path = paths["prepared"] / "qc-summary.json"
    write_json_atomic(qc_summary_path, {
        "schema_version": 1,
        "dataset_id": record.dataset_id,
        "view": "official",
        "row_count": row_count,
        "hard_failures": 0,
        "flag_counts": dict(sorted(flag_counts.items())),
    })
    lock = {
        "schema_version": 1,
        "dataset_id": record.dataset_id,
        "version": record.version,
        "source_release": source_release,
        "source_revision": None,
        "source_split": record.source_split,
        "source_config": locale,
        "license_spdx": record.license.spdx,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "adapter_version": ADAPTER_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "row_count": row_count,
        "source_manifest_sha256": sha256_file(test_tsv),
        "source_archive_sha256": archive_info["sha256"],
        "prepared_manifest_sha256": manifest_hash,
        "tool_versions": {
            "python": sys.version.split()[0],
            "ffmpeg": ffmpeg_version(),
            "datacollective": _package_version("datacollective"),
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


def verify_prepared_common_voice(
    record: DatasetRecord, data_root: str | Path,
) -> PreparedDataset:
    paths = _dataset_paths(Path(data_root), record)
    lock_path = paths["prepared"] / "dataset.lock.json"
    manifest_path = paths["prepared"] / "manifest.jsonl"
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetPreparationError("prepared Common Voice lock is missing or invalid") from exc
    rows = load_manifest(manifest_path)
    expected = record.expected.get("rows")
    if len(rows) != expected or lock.get("row_count") != expected:
        raise DatasetPreparationError("prepared Common Voice row count does not match registry")
    manifest_hash = sha256_file(manifest_path)
    if lock.get("prepared_manifest_sha256") != manifest_hash:
        raise DatasetPreparationError("prepared Common Voice manifest hash does not match lock")
    if lock.get("version") != record.version or lock.get("source_split") != "test":
        raise DatasetPreparationError("prepared Common Voice version or split does not match registry")
    if any("client_id" in row.get("metadata", {}) for row in rows):
        raise DatasetPreparationError("prepared Common Voice manifest exposes client_id")
    missing = [
        row["sample_id"] for row in rows
        if not (paths["prepared"] / row["audio_path"]).is_file()
    ]
    if missing:
        raise DatasetPreparationError(f"prepared Common Voice audio is missing: {missing[0]}")
    return PreparedDataset(
        dataset_id=record.dataset_id,
        manifest_path=manifest_path,
        lock_path=lock_path,
        row_count=len(rows),
        manifest_sha256=manifest_hash,
        qc_summary_path=paths["prepared"] / "qc-summary.json",
    )
