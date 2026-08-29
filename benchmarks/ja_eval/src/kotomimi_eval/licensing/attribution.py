from __future__ import annotations

from .registry import DatasetRecord


def attribution_requirement(record: DatasetRecord) -> dict[str, str | bool]:
    """Return machine-readable attribution requirements without acquiring data."""
    return {
        "dataset_id": record.dataset_id,
        "required": record.license.attribution_required,
        "spdx": record.license.spdx,
        "source_url": record.source_url,
    }
