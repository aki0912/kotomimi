from __future__ import annotations

import json

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from .errors import DatasetPreparationError
from .paths import SCHEMA_DIR


def validate_schema(instance: object, schema_name: str) -> None:
    path = SCHEMA_DIR / schema_name
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(instance)
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        raise DatasetPreparationError(f"invalid benchmark schema {schema_name}: {exc}") from exc
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "root"
        raise DatasetPreparationError(
            f"{schema_name} validation failed at {location}: {exc.message}") from exc
