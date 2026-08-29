from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import EvaluationConfigError


def load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    try:
        value = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EvaluationConfigError(f"cannot read config {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise EvaluationConfigError(f"invalid YAML in {config_path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvaluationConfigError(f"config {config_path} must contain a mapping")
    if value.get("schema_version") != 1:
        raise EvaluationConfigError(f"config {config_path} must use schema_version 1")
    return value
