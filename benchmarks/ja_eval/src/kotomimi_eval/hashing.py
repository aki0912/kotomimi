from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_sample_id(dataset_id: str, version: str, split: str, source_sample_id: str) -> str:
    value = "\0".join((dataset_id, version, split, source_sample_id))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
