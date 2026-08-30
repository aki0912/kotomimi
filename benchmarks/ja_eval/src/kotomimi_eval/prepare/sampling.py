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


def _common_voice_stratum(row: dict) -> tuple[str, str, str, str, str]:
    metadata = row.get("metadata", {})
    duration = float(row["duration_s"])
    duration_bin = "short" if duration < 3 else "medium" if duration <= 8 else "long"
    return (
        duration_bin,
        str(metadata.get("vote_margin_bin") or "unknown"),
        str(metadata.get("sentence_domain") or "unknown"),
        str(metadata.get("age") or "unknown"),
        str(metadata.get("gender") or "unknown"),
    )


def deterministic_common_voice_sample(rows: list[dict], count: int, seed: int) -> list[dict]:
    """Proportionally sample CV metadata strata while spreading speakers."""
    if count < 0 or count > len(rows):
        raise ValueError("sample count is outside available rows")
    groups: dict[tuple[str, str, str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[_common_voice_stratum(row)].append(row)
    if not rows:
        return []
    exact = {key: count * len(group) / len(rows) for key, group in groups.items()}
    quotas = {key: math.floor(value) for key, value in exact.items()}
    remainder = count - sum(quotas.values())
    quota_order = sorted(groups, key=lambda key: (-(exact[key] - quotas[key]), key))
    for key in quota_order[:remainder]:
        quotas[key] += 1

    selected: list[dict] = []
    speaker_counts: dict[str, int] = defaultdict(int)
    for key in sorted(groups):
        available = list(groups[key])
        for _ in range(quotas[key]):
            chosen = min(
                available,
                key=lambda row: (
                    speaker_counts[str(row.get("speaker_id") or row["sample_id"])],
                    stable_score(seed, row["sample_id"]),
                ),
            )
            available.remove(chosen)
            speaker = str(chosen.get("speaker_id") or chosen["sample_id"])
            speaker_counts[speaker] += 1
            selected.append(chosen)
    return sorted(selected, key=lambda row: stable_score(seed, row["sample_id"]))
