from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from ..errors import DatasetPreparationError
from ..hashing import sha256_file


def canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_jsonl_atomic(path: str | Path, rows: Iterable[dict]) -> tuple[int, str]:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_name(output.name + ".part")
    count = 0
    try:
        if part.exists():
            part.unlink()
        with part.open("x", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(canonical_json(row) + "\n")
                count += 1
        os.replace(part, output)
    finally:
        if part.exists():
            part.unlink()
    return count, sha256_file(output)


def write_json_atomic(path: str | Path, value: dict) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_name(output.name + ".part")
    try:
        part.write_text(
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
            encoding="utf-8")
        os.replace(part, output)
    finally:
        if part.exists():
            part.unlink()
    return sha256_file(output)


def load_manifest(path: str | Path) -> list[dict]:
    manifest_path = Path(path)
    rows = []
    seen_ids = set()
    try:
        with manifest_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise DatasetPreparationError(
                        f"manifest row {line_number} is not an object")
                sample_id = row.get("sample_id")
                if sample_id in seen_ids:
                    raise DatasetPreparationError(f"duplicate manifest sample_id: {sample_id}")
                seen_ids.add(sample_id)
                rows.append(row)
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetPreparationError(f"cannot read manifest {manifest_path.name}: {exc}") from exc
    return rows
