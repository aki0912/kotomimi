import json
from pathlib import Path

import pytest
import yaml

from kotomimi_eval.errors import EvaluationConfigError
from kotomimi_eval.hashing import stable_sample_id
from kotomimi_eval.licensing.registry import load_registry


def test_registry_pins_fleurs_revision_split_and_count():
    record = load_registry().get("fleurs_ja")
    assert record.raw["source_repo"] == "google/fleurs"
    assert record.raw["source_revision"] == "70bb2e84b976b7e960aa89f1c648e09c59f894dd"
    assert record.raw["source_config"] == "ja_jp"
    assert record.source_split == "test"
    assert record.expected["rows"] == 650


def test_registry_pins_common_voice_release_and_test_count():
    record = load_registry().get("common_voice_ja_26")
    assert record.version == "26.0"
    assert record.source_split == "test"
    assert record.expected["rows"] == 9020
    assert "no_speaker_reidentification" in record.license.restrictions
    assert not record.license.redistribute_raw


def test_allowed_and_denied_registries_cannot_overlap(tmp_path):
    allowed = tmp_path / "datasets.yaml"
    denied = tmp_path / "denied.yaml"
    allowed.write_text("schema_version: 1\ndatasets:\n  same: {}\n", encoding="utf-8")
    denied.write_text(
        "schema_version: 1\ndatasets:\n  same:\n    display_name: same\n"
        "    reason_code: unknown\n    reason: unknown\n    source_url: https://example.test\n",
        encoding="utf-8")
    with pytest.raises(EvaluationConfigError, match="both allowed and denied"):
        load_registry(allowed, denied)


def test_missing_source_url_fails_registry_load(tmp_path):
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / "config" / "datasets.yaml").read_text(encoding="utf-8"))
    del data["datasets"]["fleurs_ja"]["source_url"]
    datasets = tmp_path / "datasets.yaml"
    datasets.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(EvaluationConfigError, match="source_url"):
        load_registry(datasets, root / "config" / "denied_datasets.yaml")


def test_non_https_source_url_fails_registry_load(tmp_path):
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / "config" / "datasets.yaml").read_text(encoding="utf-8"))
    data["datasets"]["fleurs_ja"]["source_url"] = "http://example.test/fleurs"
    datasets = tmp_path / "datasets.yaml"
    datasets.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(EvaluationConfigError, match="public HTTPS URL"):
        load_registry(datasets, root / "config" / "denied_datasets.yaml")


def test_every_schema_is_json_and_version_one():
    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    schemas = sorted(schema_dir.glob("*.schema.json"))
    assert {path.name for path in schemas} == {
        "audit.schema.json", "dataset_lock.schema.json",
        "manifest.schema.json", "report.schema.json",
    }
    for path in schemas:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$schema"].endswith("2020-12/schema")
        assert schema["properties"]["schema_version"]["const"] == 1


def test_sample_id_is_stable_and_uses_all_identity_fields():
    first = stable_sample_id("fleurs_ja", "rev", "test", "42")
    assert first == stable_sample_id("fleurs_ja", "rev", "test", "42")
    assert len(first) == 64
    assert first != stable_sample_id("fleurs_ja", "rev", "validation", "42")
