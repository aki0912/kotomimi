from __future__ import annotations

from pathlib import Path

from ..prepare.manifest import write_json_atomic
from ..schema_validation import validate_schema


def write_report_json(path: str | Path, report: dict) -> str:
    required = {"schema_version", "run_id", "suite", "system", "environment",
                "metrics", "datasets", "subsets", "failures"}
    missing = required - set(report)
    if missing:
        raise ValueError(f"report is missing required fields: {sorted(missing)}")
    if report["schema_version"] != 1:
        raise ValueError("report schema_version must be 1")
    validate_schema(report, "report.schema.json")
    return write_json_atomic(path, report)
