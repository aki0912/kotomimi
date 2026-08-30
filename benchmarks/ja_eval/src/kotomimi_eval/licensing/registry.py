from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..config import load_yaml_mapping
from ..errors import EvaluationConfigError, LicensePolicyError
from ..paths import CONFIG_DIR


POLICIES = frozenset({"strict", "sharealike", "manual-review"})


@dataclass(frozen=True)
class LicenseRecord:
    spdx: str
    policy: str
    commercial_use: bool
    attribution_required: bool
    redistribute_raw: bool
    share_alike: bool = False
    restrictions: tuple[str, ...] = ()
    additional_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatasetRecord:
    dataset_id: str
    display_name: str
    adapter: str
    version: str
    source_split: str
    source_url: str
    license: LicenseRecord
    acquisition: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class DeniedDataset:
    dataset_id: str
    display_name: str
    reason_code: str
    reason: str
    source_url: str


@dataclass(frozen=True)
class DatasetRegistry:
    datasets: dict[str, DatasetRecord]
    denied: dict[str, DeniedDataset]

    def get(self, dataset_id: str) -> DatasetRecord:
        if dataset_id in self.denied:
            item = self.denied[dataset_id]
            raise LicensePolicyError(
                f"dataset {dataset_id!r} is denied: {item.reason_code}: {item.reason}")
        try:
            return self.datasets[dataset_id]
        except KeyError as exc:
            raise LicensePolicyError(f"unknown dataset {dataset_id!r}; registration is required") from exc


def _required_string(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvaluationConfigError(f"{context}.{key} must be a non-empty string")
    return value


def _string_tuple(data: dict[str, Any], key: str, context: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise EvaluationConfigError(f"{context}.{key} must be a list of non-empty strings")
    return tuple(value)


def _parse_dataset(dataset_id: str, raw: Any) -> DatasetRecord:
    context = f"datasets.{dataset_id}"
    if not isinstance(raw, dict):
        raise EvaluationConfigError(f"{context} must be a mapping")
    license_raw = raw.get("license")
    if not isinstance(license_raw, dict):
        raise EvaluationConfigError(f"{context}.license must be a mapping")
    policy = _required_string(license_raw, "policy", f"{context}.license")
    if policy not in POLICIES:
        raise EvaluationConfigError(f"{context}.license.policy is unknown: {policy}")
    for boolean_key in ("commercial_use", "attribution_required", "redistribute_raw"):
        if not isinstance(license_raw.get(boolean_key), bool):
            raise EvaluationConfigError(f"{context}.license.{boolean_key} must be boolean")
    share_alike = license_raw.get("share_alike", False)
    if not isinstance(share_alike, bool):
        raise EvaluationConfigError(f"{context}.license.share_alike must be boolean")
    version = raw.get("version") or raw.get("source_revision")
    if not isinstance(version, str) or not version:
        raise EvaluationConfigError(f"{context}.version or source_revision is required")
    acquisition = raw.get("acquisition", {})
    expected = raw.get("expected", {})
    if not isinstance(acquisition, dict) or not isinstance(expected, dict):
        raise EvaluationConfigError(f"{context}.acquisition and expected must be mappings")
    source_url = _required_string(raw, "source_url", context)
    parsed_url = urlparse(source_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc or parsed_url.username:
        raise EvaluationConfigError(f"{context}.source_url must be a public HTTPS URL")
    return DatasetRecord(
        dataset_id=dataset_id,
        display_name=_required_string(raw, "display_name", context),
        adapter=_required_string(raw, "adapter", context),
        version=version,
        source_split=_required_string(raw, "source_split", context),
        source_url=source_url,
        license=LicenseRecord(
            spdx=_required_string(license_raw, "spdx", f"{context}.license"),
            policy=policy,
            commercial_use=license_raw["commercial_use"],
            attribution_required=license_raw["attribution_required"],
            redistribute_raw=license_raw["redistribute_raw"],
            share_alike=share_alike,
            restrictions=_string_tuple(license_raw, "restrictions", f"{context}.license"),
            additional_terms=_string_tuple(license_raw, "additional_terms", f"{context}.license"),
        ),
        acquisition=acquisition,
        expected=expected,
        raw=dict(raw),
    )


def load_registry(
    datasets_path: str | Path | None = None,
    denied_path: str | Path | None = None,
) -> DatasetRegistry:
    datasets_data = load_yaml_mapping(datasets_path or CONFIG_DIR / "datasets.yaml")
    denied_data = load_yaml_mapping(denied_path or CONFIG_DIR / "denied_datasets.yaml")
    raw_datasets = datasets_data.get("datasets")
    raw_denied = denied_data.get("datasets")
    if not isinstance(raw_datasets, dict) or not isinstance(raw_denied, dict):
        raise EvaluationConfigError("dataset registries must contain a datasets mapping")
    overlap = set(raw_datasets) & set(raw_denied)
    if overlap:
        raise EvaluationConfigError(f"datasets cannot be both allowed and denied: {sorted(overlap)}")
    datasets = {key: _parse_dataset(key, value) for key, value in raw_datasets.items()}
    denied: dict[str, DeniedDataset] = {}
    for dataset_id, raw in raw_denied.items():
        context = f"denied.datasets.{dataset_id}"
        if not isinstance(raw, dict):
            raise EvaluationConfigError(f"{context} must be a mapping")
        denied[dataset_id] = DeniedDataset(
            dataset_id=dataset_id,
            display_name=_required_string(raw, "display_name", context),
            reason_code=_required_string(raw, "reason_code", context),
            reason=_required_string(raw, "reason", context),
            source_url=_required_string(raw, "source_url", context),
        )
    return DatasetRegistry(datasets=datasets, denied=denied)
