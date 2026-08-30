from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PreparedDataset:
    dataset_id: str
    manifest_path: Path
    lock_path: Path
    row_count: int
    manifest_sha256: str
    qc_summary_path: Path
