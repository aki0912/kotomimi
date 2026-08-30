from dataclasses import replace
import json

import pytest

from kotomimi_eval.errors import LicensePolicyError
from kotomimi_eval.licensing.policy import check_dataset_license
from kotomimi_eval.licensing.registry import LicenseRecord, load_registry


def test_strict_core_datasets_are_allowed():
    registry = load_registry()
    for dataset_id in ("common_voice_ja_26", "fleurs_ja", "spreds_u1_ja"):
        decision = check_dataset_license(registry.get(dataset_id))
        assert decision.allowed
        assert decision.policy == "strict"


@pytest.mark.parametrize("dataset_id", ["cpjd", "jvnv", "jnv"])
def test_sharealike_requires_explicit_opt_in(dataset_id):
    record = load_registry().get(dataset_id)
    with pytest.raises(LicensePolicyError, match="allow-sharealike"):
        check_dataset_license(record)
    assert check_dataset_license(record, allow_sharealike=True).allowed


def _write_approval(path, **overrides):
    data = {
        "schema_version": 1,
        "dataset_id": "ita_rion",
        "approved_by": "organization-review",
        "approved_at": "2026-08-29",
        "purpose": "internal commercial ASR evaluation",
        "terms_reviewed": ["CC-BY-4.0", "no resale"],
        "allow_redistribution": False,
        "notes": "Audio remains local.",
    }
    data.update(overrides)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_manual_review_requires_complete_local_approval(tmp_path):
    record = load_registry().get("ita_rion")
    with pytest.raises(LicensePolicyError, match="approval"):
        check_dataset_license(record)
    approval = tmp_path / "ita_rion.json"
    _write_approval(approval)
    decision = check_dataset_license(record, approval_path=approval)
    assert decision.allowed and decision.approval_used


@pytest.mark.parametrize("overrides", [
    {"schema_version": 2},
    {"dataset_id": "another_dataset"},
    {"approved_by": ""},
    {"terms_reviewed": ["CC-BY-4.0"]},
    {"allow_redistribution": "no"},
])
def test_manual_review_rejects_invalid_or_incomplete_approval(tmp_path, overrides):
    approval = tmp_path / "ita_rion.json"
    _write_approval(approval, **overrides)
    with pytest.raises(LicensePolicyError):
        check_dataset_license(load_registry().get("ita_rion"), approval_path=approval)


def test_unknown_dataset_is_rejected():
    with pytest.raises(LicensePolicyError, match="unknown dataset"):
        load_registry().get("not_registered")


@pytest.mark.parametrize("dataset_id", [
    "reazonspeech_dataset", "jsut", "jvs", "jsss", "jecs", "j_chat",
    "csj", "cejc", "tedxjp_10k", "jtubespeech", "magichub_free_ja",
    "unknown_huggingface_mirror",
])
def test_denied_registry_never_returns_an_allowed_record(dataset_id):
    with pytest.raises(LicensePolicyError, match="is denied"):
        load_registry().get(dataset_id)


@pytest.mark.parametrize("spdx,commercial,terms", [
    ("CC-BY-NC-4.0", True, ()),
    ("CC-BY-4.0", False, ()),
    ("LicenseRef-Research-Only", True, ()),
    ("CC-BY-4.0", True, ("article_30_4_only",)),
])
def test_forbidden_terms_cannot_be_made_strict(spdx, commercial, terms):
    base = load_registry().get("fleurs_ja")
    bad_license = replace(
        base.license, spdx=spdx, commercial_use=commercial, additional_terms=terms)
    with pytest.raises(LicensePolicyError):
        check_dataset_license(replace(base, license=bad_license))


def test_manual_approval_cannot_override_forbidden_spdx(tmp_path):
    base = load_registry().get("ita_rion")
    record = replace(base, license=replace(base.license, spdx="CC-BY-NC-4.0"))
    approval = tmp_path / "ita_rion.json"
    _write_approval(approval, terms_reviewed=["CC-BY-NC-4.0", "no resale"])
    with pytest.raises(LicensePolicyError):
        check_dataset_license(record, approval_path=approval)


def test_strict_policy_rejects_unreviewed_additional_terms():
    base = load_registry().get("fleurs_ja")
    license_record = LicenseRecord(
        spdx="CC-BY-4.0", policy="strict", commercial_use=True,
        attribution_required=True, redistribute_raw=False,
        additional_terms=("no_resale",),
    )
    with pytest.raises(LicensePolicyError, match="manual-review"):
        check_dataset_license(replace(base, license=license_record))


def test_strict_policy_rejects_unknown_operational_restriction():
    base = load_registry().get("fleurs_ja")
    record = replace(base, license=replace(base.license, restrictions=("new_vendor_term",)))
    with pytest.raises(LicensePolicyError, match="manual-review"):
        check_dataset_license(record)
