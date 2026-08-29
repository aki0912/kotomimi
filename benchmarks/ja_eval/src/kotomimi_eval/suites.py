from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_yaml_mapping
from .errors import EvaluationConfigError, LicensePolicyError
from .licensing.policy import check_dataset_license
from .licensing.registry import DatasetRegistry
from .paths import CONFIG_DIR


@dataclass(frozen=True)
class SuiteRecord:
    name: str
    version: int
    seed: int
    allowed_policies: tuple[str, ...]
    datasets: dict[str, dict[str, Any]]
    requires_sharealike_opt_in: bool = False


def load_suites(path: str | Path | None = None) -> dict[str, SuiteRecord]:
    data = load_yaml_mapping(path or CONFIG_DIR / "suites.yaml")
    raw_suites = data.get("suites")
    if not isinstance(raw_suites, dict):
        raise EvaluationConfigError("suites config must contain a suites mapping")
    suites = {}
    for name, raw in raw_suites.items():
        if not isinstance(raw, dict) or not isinstance(raw.get("datasets"), dict):
            raise EvaluationConfigError(f"suite {name} must contain a datasets mapping")
        allowed = raw.get("allowed_policies")
        if not isinstance(allowed, list) or not allowed or any(not isinstance(x, str) for x in allowed):
            raise EvaluationConfigError(f"suite {name} must declare allowed_policies")
        if not isinstance(raw.get("version"), int) or not isinstance(raw.get("seed"), int):
            raise EvaluationConfigError(f"suite {name} requires integer version and seed")
        suites[name] = SuiteRecord(
            name=name,
            version=raw["version"],
            seed=raw["seed"],
            allowed_policies=tuple(allowed),
            datasets=dict(raw["datasets"]),
            requires_sharealike_opt_in=bool(raw.get("requires_sharealike_opt_in", False)),
        )
    return suites


def validate_suite_licenses(
    suite: SuiteRecord,
    registry: DatasetRegistry,
    *,
    allow_sharealike: bool = False,
) -> None:
    if suite.requires_sharealike_opt_in and not allow_sharealike:
        raise LicensePolicyError(f"suite {suite.name!r} requires explicit sharealike opt-in")
    for dataset_id in suite.datasets:
        record = registry.get(dataset_id)
        if record.license.policy not in suite.allowed_policies:
            raise LicensePolicyError(
                f"suite {suite.name!r} does not allow policy {record.license.policy!r} "
                f"for {dataset_id}")
        if record.license.policy == "manual-review":
            raise LicensePolicyError(
                f"suite {suite.name!r} cannot authorize manual-review data without an approval")
        check_dataset_license(record, allow_sharealike=allow_sharealike)
