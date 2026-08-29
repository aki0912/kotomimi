from __future__ import annotations

from pathlib import Path
from typing import Any
import os

import yaml

from .errors import EvaluationConfigError


def load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    display_path = Path(os.path.relpath(config_path, Path.cwd())).as_posix()
    try:
        value = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EvaluationConfigError(f"cannot read config {display_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise EvaluationConfigError(f"invalid YAML in {display_path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvaluationConfigError(f"config {display_path} must contain a mapping")
    if value.get("schema_version") != 1:
        raise EvaluationConfigError(f"config {display_path} must use schema_version 1")
    return value
