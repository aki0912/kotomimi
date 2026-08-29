from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import re
import unicodedata

import numpy as np
import soundfile as sf

from ..config import load_yaml_mapping
from ..errors import DatasetPreparationError
from ..hashing import sha256_file
from ..licensing.policy import check_dataset_license
from ..licensing.registry import DatasetRecord
from ..paths import CONFIG_DIR, safe_relative_parts
from ..prepare.manifest import load_manifest, write_json_atomic, write_jsonl_atomic
from ..prepare.text import has_forbidden_control, text_qc_flags
from ..schema_validation import validate_schema
from .reporting import render_qc_html, render_qc_markdown


SPEECH_ACTIVITY_METHOD = "20ms-frame-rms>=configured-dbfs"


def _dbfs(value: float) -> float | None:
    return 20 * math.log10(value) if value > 0 else None


def _audio_activity(path: Path, thresholds: dict) -> tuple[dict, list[str], str]:
    try:
        pcm, sample_rate = sf.read(str(path), dtype="int16", always_2d=False)
        info = sf.info(str(path))
    except (OSError, RuntimeError) as exc:
        raise DatasetPreparationError(f"cannot decode prepared audio {path.name}") from exc
    if pcm.ndim != 1 or not len(pcm) or info.channels != 1 or sample_rate <= 0:
        raise DatasetPreparationError(f"prepared audio is empty or not mono: {path.name}")
    if (info.format != "FLAC" or info.subtype != "PCM_16"
            or sample_rate != 16000 or info.channels != 1):
        raise DatasetPreparationError(f"prepared audio format is not standard: {path.name}")
    floats = pcm.astype(np.float32) / 32768.0
    if not np.isfinite(floats).all():
        raise DatasetPreparationError(f"prepared audio contains NaN or Inf: {path.name}")
    duration = len(pcm) / sample_rate
    if not thresholds["hard_min_duration_s"] <= duration <= thresholds["hard_max_duration_s"]:
        raise DatasetPreparationError(f"prepared audio duration is outside hard limits: {path.name}")
    frame_samples = max(1, round(sample_rate * thresholds["speech_frame_ms"] / 1000))
    frame_count = math.ceil(len(floats) / frame_samples)
    padded = np.pad(floats, (0, frame_count * frame_samples - len(floats)))
    frames = padded.reshape(frame_count, frame_samples)
    frame_rms = np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1))
    threshold_linear = 10 ** (thresholds["speech_frame_dbfs"] / 20)
    speech = frame_rms >= threshold_linear
    speech_fraction = float(np.mean(speech))
    if np.any(speech):
        first = int(np.argmax(speech))
        last = len(speech) - 1 - int(np.argmax(speech[::-1]))
        leading = first * frame_samples / sample_rate
        trailing = max(0.0, duration - min(duration, (last + 1) * frame_samples / sample_rate))
    else:
        leading = trailing = duration
    full_rms = float(np.sqrt(np.mean(np.square(floats, dtype=np.float64))))
    rms_dbfs = _dbfs(full_rms)
    peak = float(np.max(np.abs(floats)))
    clipped = float(np.mean(np.abs(floats) >= thresholds["clipping_amplitude"]))
    dc_offset = float(abs(np.mean(floats, dtype=np.float64)))
    flags = []
    if duration < thresholds["too_short_s"]:
        flags.append("too_short")
    if duration > thresholds["too_long_s"]:
        flags.append("too_long")
    if rms_dbfs is None or rms_dbfs < thresholds["very_quiet_dbfs"]:
        flags.append("very_quiet")
    if rms_dbfs is not None and rms_dbfs > thresholds["very_loud_dbfs"]:
        flags.append("very_loud")
    if clipped >= thresholds["clipping_fraction"]:
        flags.append("possible_clipping")
    if dc_offset > thresholds["dc_offset"]:
        flags.append("dc_offset")
    if leading > thresholds["leading_silence_s"]:
        flags.append("long_leading_silence")
    if trailing > thresholds["trailing_silence_s"]:
        flags.append("long_trailing_silence")
    if speech_fraction < thresholds["low_speech_fraction"]:
        flags.append("low_speech_fraction")
    if speech_fraction > thresholds["high_speech_fraction"]:
        flags.append("high_speech_fraction")
    pcm_bytes = np.asarray(pcm, dtype="<i2").tobytes()
    return ({
        "rms_dbfs": rms_dbfs,
        "peak": peak,
        "clipped_fraction": clipped,
        "dc_offset": dc_offset,
        "leading_silence_s": leading,
        "trailing_silence_s": trailing,
        "speech_fraction": speech_fraction,
        "speech_activity_method": SPEECH_ACTIVITY_METHOD,
        "decoded_duration_s": duration,
        "decoded_sample_rate": sample_rate,
        "decoded_channels": info.channels,
    }, flags, hashlib.sha256(pcm_bytes).hexdigest())


def _is_japanese_or_ascii_alnum(char: str) -> bool:
    code = ord(char)
    return (
        char.isascii() and char.isalnum()
        or 0x3040 <= code <= 0x30FF
        or 0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or char in "々〆ヶー"
    )


def _supplemental_text_flags(raw: str, evaluated: str, thresholds: dict) -> list[str]:
    flags = []
    if has_forbidden_control(raw):
        flags.append("unexpected_control_char")
    meaningful = [
        char for char in evaluated
        if not char.isspace() and not unicodedata.category(char).startswith(("P", "C"))
    ]
    if meaningful:
        ratio = sum(_is_japanese_or_ascii_alnum(char) for char in meaningful) / len(meaningful)
        if ratio < thresholds["minimum_language_char_ratio"]:
            flags.append("low_japanese_ratio")
    if re.search(r"(.)\1{4,}", evaluated):
        flags.append("repeated_chars")
    return flags


def _duplicate_groups(rows: list[dict], key_function) -> list[list[int]]:
    groups: dict[object, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        key = key_function(row)
        if key is not None and key != "":
            groups[key].append(index)
    return [indexes for indexes in groups.values() if len(indexes) > 1]


def _duplicate_summary(groups: list[list[int]]) -> dict[str, int]:
    return {"groups": len(groups), "affected_rows": sum(len(group) for group in groups)}


def _reference_digest(rows: list[dict]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(row["sample_id"].encode("ascii"))
        digest.update(b"\0")
        digest.update(row["reference_raw"].encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    try:
        part.write_text(text, encoding="utf-8", newline="\n")
        part.replace(path)
    finally:
        if part.exists():
            part.unlink()


def run_qc(
    record: DatasetRecord,
    data_root: str | Path,
    artifact_root: str | Path,
) -> tuple[dict, Path]:
    check_dataset_license(record)
    data_root_path = Path(data_root)
    prepared = data_root_path / "prepared" / record.dataset_id / record.version
    input_manifest = prepared / "manifest.jsonl"
    rows = load_manifest(input_manifest)
    expected = record.expected.get("rows")
    if isinstance(expected, int) and len(rows) != expected:
        raise DatasetPreparationError(
            f"QC input row count changed: expected {expected}, got {len(rows)}")
    config = load_yaml_mapping(CONFIG_DIR / "qc_thresholds.yaml")
    audio_thresholds = config["audio"]
    text_thresholds = config["text"]
    clean_exclude = frozenset(config["clean"]["exclude_flags"])
    enriched = [deepcopy(row) for row in rows]
    hard_failures: list[dict[str, str]] = []
    hard_ids: set[str] = set()

    for row in enriched:
        if row.get("source_split") != record.source_split:
            hard_ids.add(row["sample_id"])
            hard_failures.append({
                "sample_id": row["sample_id"],
                "error": "unexpected source split in prepared manifest",
            })

    source_id_groups = _duplicate_groups(enriched, lambda row: row["source_sample_id"])
    for group in source_id_groups:
        for index in group:
            hard_ids.add(enriched[index]["sample_id"])
            hard_failures.append({
                "sample_id": enriched[index]["sample_id"],
                "error": "duplicate source sample ID",
            })

    for row in enriched:
        sample_id = row["sample_id"]
        if sample_id in hard_ids:
            continue
        if (not row["reference_raw"] or has_forbidden_control(row["reference_raw"])
                or not row["reference_eval"]):
            hard_ids.add(sample_id)
            hard_failures.append({"sample_id": sample_id, "error": "invalid reference text"})
            continue
        try:
            relative_audio = safe_relative_parts(row["audio_path"])
        except ValueError:
            hard_ids.add(sample_id)
            hard_failures.append({"sample_id": sample_id, "error": "unsafe audio path"})
            continue
        audio_path = prepared.joinpath(*relative_audio)
        try:
            details, audio_flags, pcm_sha256 = _audio_activity(audio_path, audio_thresholds)
        except DatasetPreparationError as exc:
            hard_ids.add(sample_id)
            hard_failures.append({"sample_id": sample_id, "error": str(exc)})
            continue
        if pcm_sha256 != row["pcm_sha256"]:
            hard_ids.add(sample_id)
            hard_failures.append({"sample_id": sample_id, "error": "prepared PCM hash changed"})
            continue
        if sha256_file(audio_path) != row["audio_sha256"]:
            hard_ids.add(sample_id)
            hard_failures.append({"sample_id": sample_id, "error": "prepared audio hash changed"})
            continue
        if (details["decoded_sample_rate"] != row["sample_rate"]
                or details["decoded_channels"] != row["channels"]
                or abs(details["decoded_duration_s"] - row["duration_s"]) > 1 / row["sample_rate"]):
            hard_ids.add(sample_id)
            hard_failures.append({"sample_id": sample_id, "error": "decoded audio metadata changed"})
            continue
        text_flags = text_qc_flags(
            row["reference_raw"], row["reference_eval"],
            short_chars=text_thresholds["very_short_chars"],
            long_chars=text_thresholds["very_long_chars"],
            digit_heavy_ratio=text_thresholds["digit_heavy_ratio"],
        )
        text_flags.extend(_supplemental_text_flags(
            row["reference_raw"], row["reference_eval"], text_thresholds))
        row["qc"].update(details)
        row["qc"]["flags"] = sorted(set(row["qc"].get("flags", []) + audio_flags + text_flags))
        row["qc"]["hard_pass"] = True

    duplicate_definitions = {
        "source_id": source_id_groups,
        "source_audio": _duplicate_groups(enriched, lambda row: row["source_audio_sha256"]),
        "prepared_pcm": _duplicate_groups(enriched, lambda row: row["pcm_sha256"]),
        "raw_text": _duplicate_groups(enriched, lambda row: row["reference_raw"]),
        "audio_and_text": _duplicate_groups(
            enriched, lambda row: (row["pcm_sha256"], row["reference_raw"])),
        "speaker_and_text": _duplicate_groups(
            enriched,
            lambda row: ((row.get("speaker_id"), row["reference_raw"])
                         if row.get("speaker_id") else None)),
    }
    flag_for_duplicate = {
        "source_audio": "duplicate_source_audio",
        "prepared_pcm": "duplicate_pcm",
        "audio_and_text": "duplicate_audio_text",
        "speaker_and_text": "duplicate_speaker_text",
    }
    for kind, flag in flag_for_duplicate.items():
        for group in duplicate_definitions[kind]:
            for index in group:
                enriched[index]["qc"]["flags"] = sorted(set(
                    enriched[index]["qc"].get("flags", []) + [flag]))
    for group in duplicate_definitions["prepared_pcm"]:
        splits = {enriched[index]["source_split"] for index in group}
        if len(splits) > 1:
            for index in group:
                sample_id = enriched[index]["sample_id"]
                hard_ids.add(sample_id)
                hard_failures.append({
                    "sample_id": sample_id,
                    "error": "duplicate PCM appears in multiple splits",
                })

    official_rows = [row for row in enriched if row["sample_id"] not in hard_ids]
    clean_rows = [
        row for row in official_rows
        if not clean_exclude.intersection(row["qc"].get("flags", []))
    ]
    if _reference_digest(official_rows) != _reference_digest(
            [row for row in rows if row["sample_id"] not in hard_ids]):
        raise DatasetPreparationError("QC changed reference_raw in the official view")
    for row in official_rows:
        validate_schema(row, "manifest.schema.json")

    input_hash = sha256_file(input_manifest)
    view_dir = (data_root_path / "manifests" / "qc" / record.dataset_id
                / record.version / input_hash[:16])
    official_path = view_dir / "official.manifest.jsonl"
    clean_path = view_dir / "clean.manifest.jsonl"
    _, official_hash = write_jsonl_atomic(official_path, official_rows)
    _, clean_hash = write_jsonl_atomic(clean_path, clean_rows)
    flag_counts = Counter(
        flag for row in official_rows for flag in row["qc"].get("flags", []))
    report = {
        "schema_version": 1,
        "dataset_id": record.dataset_id,
        "dataset_version": record.version,
        "source_split": record.source_split,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_rows": len(rows),
        "input_manifest_sha256": input_hash,
        "reference_raw_sha256": _reference_digest(rows),
        "views": {
            "official": {
                "rows": len(official_rows),
                "manifest_sha256": official_hash,
                "manifest_relative_to_data_root": official_path.relative_to(data_root_path).as_posix(),
            },
            "clean": {
                "rows": len(clean_rows),
                "manifest_sha256": clean_hash,
                "manifest_relative_to_data_root": clean_path.relative_to(data_root_path).as_posix(),
            },
        },
        "hard_failures": hard_failures,
        "flag_counts": dict(sorted(flag_counts.items())),
        "clean_exclude_flags": sorted(clean_exclude),
        "duplicates": {
            kind: _duplicate_summary(groups)
            for kind, groups in duplicate_definitions.items()
        },
        "speech_activity": {
            "method": SPEECH_ACTIVITY_METHOD,
            "frame_ms": audio_thresholds["speech_frame_ms"],
            "threshold_dbfs": audio_thresholds["speech_frame_dbfs"],
        },
    }
    report_dir = Path(artifact_root) / "qc" / record.dataset_id / input_hash[:16]
    write_json_atomic(report_dir / "qc.json", report)
    _write_text_atomic(report_dir / "qc.md", render_qc_markdown(report))
    _write_text_atomic(report_dir / "qc.html", render_qc_html(report))
    return report, report_dir
