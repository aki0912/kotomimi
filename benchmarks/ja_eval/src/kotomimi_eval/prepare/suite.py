from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..errors import DatasetPreparationError
from ..hashing import sha256_file
from ..licensing.registry import DatasetRegistry
from ..suites import SuiteRecord, validate_suite_licenses
from .manifest import load_manifest, write_json_atomic, write_jsonl_atomic
from .sampling import deterministic_common_voice_sample, deterministic_stratified_sample


def suite_paths(data_root: Path, suite_name: str) -> tuple[Path, Path]:
    directory = data_root / "manifests" / suite_name
    return directory / "manifest.jsonl", directory / "suite.lock.json"


def build_suite(
    suite: SuiteRecord,
    registry: DatasetRegistry,
    data_root: str | Path,
    *,
    allow_sharealike: bool = False,
) -> tuple[Path, Path]:
    validate_suite_licenses(suite, registry, allow_sharealike=allow_sharealike)
    data_root_path = Path(data_root)
    selected_rows = []
    dataset_locks = {}
    for dataset_id, selection in suite.datasets.items():
        record = registry.get(dataset_id)
        prepared = data_root_path / "prepared" / dataset_id / record.version
        manifest_path = prepared / "manifest.jsonl"
        lock_path = prepared / "dataset.lock.json"
        if not manifest_path.is_file() or not lock_path.is_file():
            if selection.get("optional") or suite.name == "smoke":
                continue
            raise DatasetPreparationError(f"prepared dataset is missing: {dataset_id}")
        rows = load_manifest(manifest_path)
        count_value = selection.get("count")
        count = len(rows) if count_value == "all" else int(count_value)
        if count > len(rows):
            if selection.get("maximum_or_all"):
                count = len(rows)
            else:
                raise DatasetPreparationError(
                    f"suite {suite.name} requests {count} of {dataset_id}, only {len(rows)} exist")
        if (record.adapter == "common_voice"
                and selection.get("selection") == "deterministic_stratified_speaker_aware"):
            chosen = deterministic_common_voice_sample(rows, count, suite.seed)
        else:
            chosen = deterministic_stratified_sample(rows, count, suite.seed)
        selected_rows.extend(chosen)
        selected_ids = "\n".join(row["sample_id"] for row in chosen).encode("utf-8")
        dataset_locks[dataset_id] = {
            "manifest_sha256": sha256_file(manifest_path),
            "selected_count": len(chosen),
            "selected_ids_sha256": hashlib.sha256(selected_ids).hexdigest(),
        }
    selected_rows.sort(key=lambda row: (row["dataset_id"], row["sample_id"]))
    manifest_output, lock_output = suite_paths(data_root_path, suite.name)
    _, suite_manifest_hash = write_jsonl_atomic(manifest_output, selected_rows)
    lock = {
        "schema_version": 1,
        "suite": suite.name,
        "suite_version": suite.version,
        "seed": suite.seed,
        "manifest_sha256": suite_manifest_hash,
        "datasets": dataset_locks,
    }
    write_json_atomic(lock_output, lock)
    return manifest_output, lock_output


def verify_suite(suite: SuiteRecord, data_root: str | Path) -> dict:
    manifest_path, lock_path = suite_paths(Path(data_root), suite.name)
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetPreparationError(f"suite lock is missing or invalid: {suite.name}") from exc
    if lock.get("suite") != suite.name or lock.get("suite_version") != suite.version:
        raise DatasetPreparationError("suite lock identity does not match config")
    if lock.get("seed") != suite.seed:
        raise DatasetPreparationError("suite lock seed does not match config")
    if lock.get("manifest_sha256") != sha256_file(manifest_path):
        raise DatasetPreparationError("suite manifest hash does not match lock")
    rows = load_manifest(manifest_path)
    expected = sum(item["selected_count"] for item in lock["datasets"].values())
    if len(rows) != expected:
        raise DatasetPreparationError("suite row count does not match lock")
    return lock
