import json

from kotomimi_eval.licensing.registry import load_registry
from kotomimi_eval.prepare.manifest import load_manifest, write_json_atomic, write_jsonl_atomic
from kotomimi_eval.prepare.suite import build_suite, verify_suite
from kotomimi_eval.suites import load_suites


def _row(dataset_id: str, index: int) -> dict:
    common_voice = dataset_id == "common_voice_ja_26"
    return {
        "sample_id": f"{index + (0 if common_voice else 10000):064x}",
        "dataset_id": dataset_id,
        "duration_s": (2.0, 5.0, 9.0)[index % 3],
        "speaker_id": f"speaker-{index % 400}" if common_voice else None,
        "metadata": {
            "gender": ("female", "male")[index % 2],
            "vote_margin_bin": ("one", "two_to_three", "four_plus")[index % 3],
            "sentence_domain": ("general", "news")[index % 2],
            "age": ("twenties", "thirties", "unknown")[index % 3],
        },
    }


def _write_prepared(data_root, record, rows):
    directory = data_root / "prepared" / record.dataset_id / record.version
    write_jsonl_atomic(directory / "manifest.jsonl", rows)
    write_json_atomic(directory / "dataset.lock.json", {"fixture": True})


def test_minimum_strict_build_is_stable_with_1000_cv_and_300_fleurs(tmp_path):
    registry = load_registry()
    suite = load_suites()["minimum-strict"]
    cv_rows = [_row("common_voice_ja_26", index) for index in range(1500)]
    fleurs_rows = [_row("fleurs_ja", index) for index in range(650)]
    _write_prepared(tmp_path, registry.get("common_voice_ja_26"), cv_rows)
    _write_prepared(tmp_path, registry.get("fleurs_ja"), fleurs_rows)

    manifest, lock_path = build_suite(suite, registry, tmp_path)
    first_rows = load_manifest(manifest)
    first_lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert len(first_rows) == 1300
    assert first_lock["datasets"]["common_voice_ja_26"]["selected_count"] == 1000
    assert first_lock["datasets"]["fleurs_ja"]["selected_count"] == 300
    assert verify_suite(suite, tmp_path)["manifest_sha256"] == first_lock["manifest_sha256"]

    _write_prepared(tmp_path, registry.get("common_voice_ja_26"), reversed(cv_rows))
    _write_prepared(tmp_path, registry.get("fleurs_ja"), reversed(fleurs_rows))
    build_suite(suite, registry, tmp_path)
    second_rows = load_manifest(manifest)
    assert [row["sample_id"] for row in second_rows] == [
        row["sample_id"] for row in first_rows
    ]
