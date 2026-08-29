from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading

from ..errors import DatasetPreparationError, EvaluationConfigError
from ..hashing import sha256_file
from ..licensing.policy import check_dataset_license
from ..licensing.registry import DatasetRecord
from ..paths import safe_relative_parts
from ..prepare.manifest import canonical_json, load_manifest, write_json_atomic, write_jsonl_atomic
from ..prepare.sampling import stable_score
from ..schema_validation import validate_schema


AUDIT_LABELS = (
    "ok",
    "minor_transcript_issue",
    "major_transcript_mismatch",
    "bad_audio",
    "truncated_audio",
    "wrong_language",
    "unexpected_nonverbal",
    "duplicate",
    "uncertain",
)
NOISE_LEVELS = ("clean", "mild", "heavy")
SPEECH_STYLES = ("read", "spontaneous", "acted", "nonverbal")
_AUDIT_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_DECISION_LOCK = threading.Lock()


def audit_directory(artifact_root: str | Path, audit_id: str) -> Path:
    if not _AUDIT_ID.fullmatch(audit_id):
        raise EvaluationConfigError("audit ID contains unsafe characters")
    return Path(artifact_root) / "audits" / audit_id


def _duration_bin(duration: float) -> str:
    return "short" if duration < 3 else "medium" if duration <= 8 else "long"


def _audit_stratum(record: DatasetRecord, row: dict) -> tuple[str, ...]:
    metadata = row.get("metadata", {})
    flagged = "flagged" if row.get("qc", {}).get("flags") else "unflagged"
    if record.adapter == "common_voice":
        return (
            _duration_bin(float(row["duration_s"])),
            str(metadata.get("vote_margin_bin") or "unknown"),
            str(metadata.get("sentence_domain") or "unknown"),
            str(metadata.get("age") or "unknown"),
            str(metadata.get("gender") or "unknown"),
            flagged,
        )
    if record.adapter == "fleurs":
        return (
            str(row.get("speaker_id") or "speaker-unavailable"),
            _duration_bin(float(row["duration_s"])),
            flagged,
        )
    return (_duration_bin(float(row["duration_s"])), flagged)


def deterministic_audit_sample(
    record: DatasetRecord, rows: list[dict], count: int, seed: int,
) -> list[dict]:
    if count <= 0 or count > len(rows):
        raise EvaluationConfigError("audit count is outside available rows")
    groups: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for row in rows:
        groups[_audit_stratum(record, row)].append(row)
    exact = {key: count * len(group) / len(rows) for key, group in groups.items()}
    quotas = {key: math.floor(value) for key, value in exact.items()}
    remainder = count - sum(quotas.values())
    for key in sorted(groups, key=lambda item: (-(exact[item] - quotas[item]), item))[:remainder]:
        quotas[key] += 1
    speaker_counts: dict[str, int] = defaultdict(int)
    selected = []
    for key in sorted(groups):
        available = list(groups[key])
        for _ in range(quotas[key]):
            chosen = min(
                available,
                key=lambda row: (
                    speaker_counts[str(row.get("speaker_id") or row["sample_id"])],
                    stable_score(seed, row["sample_id"]),
                ),
            )
            available.remove(chosen)
            speaker_counts[str(chosen.get("speaker_id") or chosen["sample_id"])] += 1
            selected.append(chosen)
    return sorted(selected, key=lambda row: stable_score(seed, row["sample_id"]))


def _load_qc_manifest(
    record: DatasetRecord, data_root: Path, artifact_root: Path, view: str,
) -> tuple[Path, dict]:
    if view not in {"official", "clean"}:
        raise EvaluationConfigError("audit view must be official or clean")
    prepared_manifest = (data_root / "prepared" / record.dataset_id / record.version
                         / "manifest.jsonl")
    input_hash = sha256_file(prepared_manifest)
    report_path = artifact_root / "qc" / record.dataset_id / input_hash[:16] / "qc.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetPreparationError(
            f"QC report is missing for {record.dataset_id}; run qc first") from exc
    if (report.get("input_manifest_sha256") != input_hash
            or report.get("hard_failures")):
        raise DatasetPreparationError("QC report is stale or contains hard failures")
    relative = report["views"][view]["manifest_relative_to_data_root"]
    try:
        parts = safe_relative_parts(relative)
    except ValueError:
        raise DatasetPreparationError("QC report contains an unsafe manifest path")
    manifest = data_root.joinpath(*parts)
    if sha256_file(manifest) != report["views"][view]["manifest_sha256"]:
        raise DatasetPreparationError(f"QC {view} manifest hash does not match report")
    return manifest, report


def create_audit(
    record: DatasetRecord,
    data_root: str | Path,
    artifact_root: str | Path,
    *,
    count: int,
    seed: int,
    view: str = "official",
) -> tuple[dict, Path]:
    check_dataset_license(record)
    data_root_path = Path(data_root)
    artifact_root_path = Path(artifact_root)
    manifest_path, qc_report = _load_qc_manifest(
        record, data_root_path, artifact_root_path, view)
    rows = load_manifest(manifest_path)
    selected = deterministic_audit_sample(record, rows, count, seed)
    selected_ids = "\n".join(row["sample_id"] for row in selected).encode("ascii")
    view_part = "" if view == "official" else f"-{view}"
    audit_id = (f"{record.dataset_id}{view_part}-{seed}-{count}-"
                f"{qc_report['input_manifest_sha256'][:12]}")
    directory = audit_directory(artifact_root_path, audit_id)
    metadata_path = directory / "audit.json"
    samples_path = directory / "samples.jsonl"
    if metadata_path.exists() or samples_path.exists():
        try:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DatasetPreparationError("existing audit metadata is invalid") from exc
        identity = (
            "dataset_id", "dataset_version", "count", "seed", "source_view",
            "source_manifest_sha256",
        )
        proposed = {
            "dataset_id": record.dataset_id,
            "dataset_version": record.version,
            "count": count,
            "seed": seed,
            "source_view": view,
            "source_manifest_sha256": qc_report["views"][view]["manifest_sha256"],
        }
        if any(
            existing.get(key, "official" if key == "source_view" else None) != proposed[key]
            for key in identity
        ):
            raise DatasetPreparationError("refusing to overwrite a different audit")
        if (not samples_path.is_file()
                or existing.get("samples_sha256") != sha256_file(samples_path)):
            raise DatasetPreparationError("existing audit samples do not match metadata")
        return existing, directory
    row_count, samples_hash = write_jsonl_atomic(samples_path, selected)
    metadata = {
        "schema_version": 1,
        "audit_id": audit_id,
        "dataset_id": record.dataset_id,
        "dataset_version": record.version,
        "count": row_count,
        "seed": seed,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_view": view,
        "source_manifest_sha256": qc_report["views"][view]["manifest_sha256"],
        "samples_sha256": samples_hash,
        "selected_ids_sha256": hashlib.sha256(selected_ids).hexdigest(),
        "speaker_metadata": (
            "provided-hash" if any(row.get("speaker_id") for row in selected)
            else "unavailable-no-inference"
        ),
    }
    write_json_atomic(metadata_path, metadata)
    return metadata, directory


def load_audit(artifact_root: str | Path, audit_id: str) -> tuple[dict, list[dict], Path]:
    directory = audit_directory(artifact_root, audit_id)
    try:
        metadata = json.loads((directory / "audit.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetPreparationError(f"audit is missing or invalid: {audit_id}") from exc
    samples_path = directory / "samples.jsonl"
    if metadata.get("samples_sha256") != sha256_file(samples_path):
        raise DatasetPreparationError("audit samples hash does not match metadata")
    samples = load_manifest(samples_path)
    if len(samples) != metadata.get("count"):
        raise DatasetPreparationError("audit sample count does not match metadata")
    return metadata, samples, directory


def append_decision(
    artifact_root: str | Path,
    audit_id: str,
    sample_ids: set[str],
    values: dict[str, str],
) -> dict:
    sample_id = values.get("sample_id", "")
    if sample_id not in sample_ids:
        raise EvaluationConfigError("decision sample is not part of this audit")
    label = values.get("label", "")
    noise = values.get("noise_level", "")
    style = values.get("speech_style", "")
    if label not in AUDIT_LABELS or noise not in NOISE_LEVELS or style not in SPEECH_STYLES:
        raise EvaluationConfigError("audit decision contains an invalid choice")
    decision = {
        "schema_version": 1,
        "audit_id": audit_id,
        "sample_id": sample_id,
        "label": label,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "spoken_text_notes": values.get("spoken_text_notes", "")[:10_000],
        "noise_level": noise,
        "speech_style": style,
        "reviewer_comment": values.get("reviewer_comment", "")[:10_000],
    }
    validate_schema(decision, "audit.schema.json")
    decisions_path = audit_directory(artifact_root, audit_id) / "decisions.jsonl"
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (canonical_json(decision) + "\n").encode("utf-8")
    with _DECISION_LOCK:
        descriptor = os.open(decisions_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "ab") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    return decision


def load_decisions(artifact_root: str | Path, audit_id: str) -> tuple[list[dict], dict[str, dict]]:
    path = audit_directory(artifact_root, audit_id) / "decisions.jsonl"
    history = []
    latest = {}
    if not path.exists():
        return history, latest
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.endswith("\n"):
                    raise DatasetPreparationError(
                        f"audit decision line {line_number} is incomplete")
                decision = json.loads(line)
                validate_schema(decision, "audit.schema.json")
                if decision["audit_id"] != audit_id:
                    raise DatasetPreparationError("audit decision belongs to another audit")
                history.append(decision)
                latest[decision["sample_id"]] = decision
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetPreparationError("audit decisions are invalid") from exc
    return history, latest


def load_audit_status(artifact_root: str | Path, audit_id: str) -> dict:
    metadata, samples, _ = load_audit(artifact_root, audit_id)
    history, latest = load_decisions(artifact_root, audit_id)
    sample_ids = {row["sample_id"] for row in samples}
    unexpected = set(latest) - sample_ids
    if unexpected:
        raise DatasetPreparationError("audit decisions contain a sample outside the audit")
    labels = Counter(item["label"] for item in latest.values())
    total = len(samples)
    reviewed = len(latest)
    severe = sum(labels[label] for label in (
        "bad_audio", "major_transcript_mismatch", "wrong_language"))
    truncated = labels["truncated_audio"]
    complete = reviewed == total and labels["uncertain"] == 0
    approved = (
        complete
        and severe / total <= 0.05
        and truncated / total <= 0.02
    ) if total else False
    dataset_status = "pending" if not complete else "approved" if approved else "experimental"
    return {
        "schema_version": 1,
        "audit_id": audit_id,
        "dataset_id": metadata["dataset_id"],
        "source_view": metadata.get("source_view", "official"),
        "total": total,
        "reviewed": reviewed,
        "remaining": total - reviewed,
        "history_entries": len(history),
        "label_counts": dict(sorted(labels.items())),
        "complete": complete,
        "approved_for_gate": approved,
        "dataset_status": dataset_status,
        "severe_issue_rate": severe / total if total else 0.0,
        "truncated_rate": truncated / total if total else 0.0,
    }


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    try:
        part.write_text(text, encoding="utf-8", newline="\n")
        part.replace(path)
    finally:
        if part.exists():
            part.unlink()


def write_audit_report(artifact_root: str | Path, audit_id: str) -> tuple[dict, Path]:
    metadata, _, _ = load_audit(artifact_root, audit_id)
    status = load_audit_status(artifact_root, audit_id)
    report = {
        "schema_version": 1,
        "audit_id": audit_id,
        "dataset_id": metadata["dataset_id"],
        "dataset_version": metadata["dataset_version"],
        "source_view": metadata.get("source_view", "official"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest_sha256": metadata["source_manifest_sha256"],
        "samples_sha256": metadata["samples_sha256"],
        "selected_ids_sha256": metadata["selected_ids_sha256"],
        "sample_count": metadata["count"],
        "reviewed_count": status["reviewed"],
        "history_entries": status["history_entries"],
        "label_counts": status["label_counts"],
        "dataset_status": status["dataset_status"],
        "approved_for_gate": status["approved_for_gate"],
        "severe_issue_rate": status["severe_issue_rate"],
        "truncated_rate": status["truncated_rate"],
        "gate_thresholds": {
            "maximum_severe_issue_rate": 0.05,
            "maximum_truncated_rate": 0.02,
            "requires_complete_review": True,
            "requires_no_uncertain": True,
        },
        "privacy": {
            "contains_sample_ids": False,
            "contains_references": False,
            "contains_audio_paths": False,
            "contains_speaker_ids": False,
        },
    }
    directory = Path(artifact_root) / "audit_reports" / audit_id
    write_json_atomic(directory / "audit-report.json", report)
    label_lines = "\n".join(
        f"| `{label}` | {count} |" for label, count in report["label_counts"].items()
    ) or "| — | 0 |"
    markdown = f"""# Audit report: {audit_id}

- Dataset: `{report['dataset_id']}`
- Version: `{report['dataset_version']}`
- Source view: `{report['source_view']}`
- Status: **{report['dataset_status']}**
- Reviewed: {report['reviewed_count']} / {report['sample_count']}
- Severe issue rate: {report['severe_issue_rate']:.1%} (maximum 5.0%)
- Truncated rate: {report['truncated_rate']:.1%} (maximum 2.0%)
- Approved for gate: `{str(report['approved_for_gate']).lower()}`

The official evaluation remains available. An experimental dataset is not used
as an approved release gate, and the clean view does not replace official results.

## Labels

| label | count |
|---|---:|
{label_lines}

This aggregate report contains no sample IDs, references, audio paths, or speaker IDs.
"""
    _write_text_atomic(directory / "audit-report.md", markdown)
    return report, directory
