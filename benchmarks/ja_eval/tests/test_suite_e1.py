import json
from pathlib import Path

import pytest

from kotomimi_eval.hashing import sha256_file
from kotomimi_eval.licensing.registry import load_registry
from kotomimi_eval.prepare.manifest import write_json_atomic, write_jsonl_atomic
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
