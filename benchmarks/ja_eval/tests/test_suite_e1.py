import json

import pytest

from kotomimi_eval.hashing import sha256_file
from kotomimi_eval.licensing.registry import load_registry
from kotomimi_eval.prepare.manifest import load_manifest, write_json_atomic, write_jsonl_atomic
from kotomimi_eval.prepare.suite import build_suite, verify_suite
from kotomimi_eval.suites import SuiteRecord


def test_suite_build_is_deterministic_and_hash_locked(tmp_path):
    registry = load_registry()
    record = registry.get("fleurs_ja")
    prepared = tmp_path / "prepared" / record.dataset_id / record.version
    rows = [
        {
            "sample_id": f"{index:064x}", "dataset_id": "fleurs_ja",
            "duration_s": 2.0 + index, "metadata": {"gender": "male"},
        }
        for index in range(4)
    ]
    _, manifest_hash = write_jsonl_atomic(prepared / "manifest.jsonl", rows)
    write_json_atomic(prepared / "dataset.lock.json", {
        "schema_version": 1, "prepared_manifest_sha256": manifest_hash,
    })
    suite = SuiteRecord(
        name="fixture-fleurs", version=1, seed=20260829,
        allowed_policies=("strict",), datasets={"fleurs_ja": {"count": 2}})
    manifest, lock = build_suite(suite, registry, tmp_path)
    first_manifest = manifest.read_bytes()
    first_lock = json.loads(lock.read_text(encoding="utf-8"))
    build_suite(suite, registry, tmp_path)
    assert manifest.read_bytes() == first_manifest
    assert json.loads(lock.read_text(encoding="utf-8")) == first_lock
    assert first_lock["manifest_sha256"] == sha256_file(manifest)
    assert verify_suite(suite, tmp_path) == first_lock


def test_json_writer_rejects_nan(tmp_path):
    with pytest.raises(ValueError, match="JSON compliant"):
        write_json_atomic(tmp_path / "bad.json", {"metric": float("nan")})


def test_suite_build_uses_qc_view_and_records_both_manifest_hashes(tmp_path):
    registry = load_registry()
    record = registry.get("fleurs_ja")
    prepared = tmp_path / "prepared" / record.dataset_id / record.version
    rows = [
        {
            "sample_id": f"{index:064x}", "dataset_id": record.dataset_id,
            "duration_s": 2.0, "metadata": {"gender": "female"},
            "qc": {"flags": flags},
        }
        for index, flags in enumerate(([], ["long_leading_silence"], []))
    ]
    _, prepared_hash = write_jsonl_atomic(prepared / "manifest.jsonl", rows)
    write_json_atomic(prepared / "dataset.lock.json", {
        "schema_version": 1, "prepared_manifest_sha256": prepared_hash,
    })
    qc_dir = (tmp_path / "manifests" / "qc" / record.dataset_id / record.version
              / prepared_hash[:16])
    _, clean_hash = write_jsonl_atomic(qc_dir / "clean.manifest.jsonl", [rows[0], rows[2]])
    write_jsonl_atomic(qc_dir / "stress.manifest.jsonl", [rows[1]])
    suite = SuiteRecord(
        name="fixture-clean", version=1, seed=20260829,
        allowed_policies=("strict",),
        datasets={record.dataset_id: {"count": "all", "view": "clean"}},
        purpose="clean_candidate", quality_status="candidate",
        evaluation_view="clean", release_gate_eligible=False,
    )
    manifest, lock_path = build_suite(suite, registry, tmp_path)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    dataset_lock = lock["datasets"][record.dataset_id]
    assert [row["sample_id"] for row in load_manifest(manifest)] == [
        rows[0]["sample_id"], rows[2]["sample_id"]]
    assert dataset_lock["prepared_manifest_sha256"] == prepared_hash
    assert dataset_lock["source_manifest_sha256"] == clean_hash
    assert dataset_lock["source_view"] == "clean"


def test_suite_build_rejects_qc_view_with_wrong_flag_membership(tmp_path):
    registry = load_registry()
    record = registry.get("fleurs_ja")
    prepared = tmp_path / "prepared" / record.dataset_id / record.version
    row = {
        "sample_id": "0" * 64, "dataset_id": record.dataset_id,
        "duration_s": 2.0, "metadata": {}, "qc": {"flags": ["long_leading_silence"]},
    }
    _, prepared_hash = write_jsonl_atomic(prepared / "manifest.jsonl", [row])
    write_json_atomic(prepared / "dataset.lock.json", {
        "schema_version": 1, "prepared_manifest_sha256": prepared_hash,
    })
    qc_dir = (tmp_path / "manifests" / "qc" / record.dataset_id / record.version
              / prepared_hash[:16])
    write_jsonl_atomic(qc_dir / "clean.manifest.jsonl", [row])
    suite = SuiteRecord(
        name="fixture-clean", version=1, seed=1, allowed_policies=("strict",),
        datasets={record.dataset_id: {"count": "all", "view": "clean"}},
    )
    from kotomimi_eval.errors import DatasetPreparationError
    with pytest.raises(DatasetPreparationError, match="violates configured flag rules"):
        build_suite(suite, registry, tmp_path)
