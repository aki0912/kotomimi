from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from ..prepare.text import normalize_reference_standard


@dataclass(frozen=True)
class EditCounts:
    substitutions: int
    deletions: int
    insertions: int
    reference_chars: int

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    @property
    def cer(self) -> float:
        return self.errors / self.reference_chars if self.reference_chars else float(self.errors > 0)


def edit_counts(reference: str, hypothesis: str, *, normalize: bool) -> EditCounts:
    if normalize:
        reference = normalize_reference_standard(reference)
        hypothesis = normalize_reference_standard(hypothesis)
    rows, columns = len(reference) + 1, len(hypothesis) + 1
    costs = [[0] * columns for _ in range(rows)]
    operations = [[""] * columns for _ in range(rows)]
    for row in range(1, rows):
        costs[row][0], operations[row][0] = row, "D"
    for column in range(1, columns):
        costs[0][column], operations[0][column] = column, "I"
    for row in range(1, rows):
        for column in range(1, columns):
            if reference[row - 1] == hypothesis[column - 1]:
                costs[row][column] = costs[row - 1][column - 1]
                operations[row][column] = "M"
            else:
                costs[row][column], operations[row][column] = min((
                    (costs[row - 1][column - 1] + 1, "S"),
                    (costs[row - 1][column] + 1, "D"),
                    (costs[row][column - 1] + 1, "I"),
                ), key=lambda value: value[0])
    counts = {"S": 0, "D": 0, "I": 0}
    row, column = len(reference), len(hypothesis)
    while row or column:
        operation = operations[row][column]
        if operation in counts:
            counts[operation] += 1
        if operation in ("M", "S"):
            row -= 1
            column -= 1
        elif operation == "D":
            row -= 1
        else:
            column -= 1
    return EditCounts(counts["S"], counts["D"], counts["I"], len(reference))


def percentile(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def aggregate_rows(rows: list[dict]) -> dict:
    def sum_field(prefix: str, field: str) -> int:
        return sum(int(row[f"{prefix}_{field}"]) for row in rows)

    def metrics(prefix: str) -> dict:
        substitutions = sum_field(prefix, "substitutions")
        deletions = sum_field(prefix, "deletions")
        insertions = sum_field(prefix, "insertions")
        reference_chars = sum_field(prefix, "reference_chars")
        errors = substitutions + deletions + insertions
        return {
            "cer": errors / reference_chars if reference_chars else float(errors > 0),
            "substitutions": substitutions,
            "deletions": deletions,
            "insertions": insertions,
            "reference_chars": reference_chars,
        }

    audio_s = sum(float(row["audio_s"]) for row in rows)
    decode_s = sum(float(row["latency_ms"]) for row in rows) / 1000
    return {
        "samples": len(rows),
        "raw": metrics("raw"),
        "normalized": metrics("normalized"),
        "sentence_exact_rate": (
            sum(bool(row["sentence_exact"]) for row in rows) / len(rows) if rows else 0.0),
        "decode_failures": sum(bool(row.get("failure")) for row in rows),
        "audio_s": audio_s,
        "decode_s": decode_s,
        "rtf": decode_s / audio_s if audio_s else 0.0,
        "latency_ms_p50": percentile((row["latency_ms"] for row in rows), 0.5),
        "latency_ms_p95": percentile((row["latency_ms"] for row in rows), 0.95),
        "peak_rss_bytes": max((int(row.get("rss_bytes", 0)) for row in rows), default=0),
    }


def group_metrics(rows: list[dict], key: Callable[[dict], str]) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(key(row), []).append(row)
    return {name: aggregate_rows(group) for name, group in sorted(groups.items())}
