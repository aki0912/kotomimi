from __future__ import annotations

from collections import defaultdict
import hashlib
import math


def stable_score(seed: int, sample_id: str) -> bytes:
    return hashlib.sha256(f"{seed}\0{sample_id}".encode("utf-8")).digest()


def _stratum(row: dict) -> tuple[str, str]:
    metadata = row.get("metadata", {})
    gender = str(metadata.get("gender") or "unknown")
    duration = float(row["duration_s"])
    duration_bin = "short" if duration < 3 else "medium" if duration <= 8 else "long"
    return gender, duration_bin


def deterministic_stratified_sample(rows: list[dict], count: int, seed: int) -> list[dict]:
    if count < 0 or count > len(rows):
        raise ValueError("sample count is outside available rows")
    if count == len(rows):
        return sorted(rows, key=lambda row: stable_score(seed, row["sample_id"]))
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[_stratum(row)].append(row)
    exact = {key: count * len(group) / len(rows) for key, group in groups.items()}
    quotas = {key: math.floor(value) for key, value in exact.items()}
    remainder = count - sum(quotas.values())
    order = sorted(groups, key=lambda key: (-(exact[key] - quotas[key]), key))
    for key in order[:remainder]:
        quotas[key] += 1
    selected = []
    for key, group in groups.items():
        ranked = sorted(group, key=lambda row: stable_score(seed, row["sample_id"]))
        selected.extend(ranked[:quotas[key]])
    return sorted(selected, key=lambda row: stable_score(seed, row["sample_id"]))
