from __future__ import annotations

from ..config import load_yaml_mapping
from ..errors import EvaluationConfigError
from ..paths import BENCHMARK_ROOT
from .registry import DatasetRecord


def attribution_requirement(record: DatasetRecord) -> dict[str, str | bool]:
    """Return machine-readable attribution requirements without acquiring data."""
    sources = load_yaml_mapping(BENCHMARK_ROOT / "licenses" / "sources.yaml").get("sources")
    if not isinstance(sources, dict) or not isinstance(sources.get(record.dataset_id), dict):
        raise EvaluationConfigError(f"attribution source missing for {record.dataset_id}")
    source = sources[record.dataset_id]
    required = ("title", "creator", "license", "source_url")
    if any(not isinstance(source.get(key), str) or not source[key] for key in required):
        raise EvaluationConfigError(f"attribution source incomplete for {record.dataset_id}")
    if source["license"] != record.license.spdx or source["source_url"] != record.source_url:
        raise EvaluationConfigError(f"attribution source does not match registry for {record.dataset_id}")
    return {
        "dataset_id": record.dataset_id,
        "required": record.license.attribution_required,
        "spdx": record.license.spdx,
        "source_url": record.source_url,
        "title": source["title"],
        "creator": source["creator"],
    }
