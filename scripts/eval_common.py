"""Shared model-free helpers and Japanese ASR evaluation metrics.

The legacy cache and ``manifest.json`` helpers remain shared by the existing
evaluation scripts.  PR 0 adds normalization and scoring functions here so
they can be tested without importing sherpa-onnx or loading models.
"""

from __future__ import annotations

import json
import os
import re
import string
import unicodedata
from dataclasses import dataclass
from typing import Iterable


_PUNCT_RE = re.compile(
    "[" + re.escape(string.punctuation)
    + "\u3000-\u303f\uff01-\uff0f\uff1a-\uff20\uff3b-\uff40\uff5b-\uff65]"
)
_DIGIT_RE = re.compile(r"\d+(?:\.\d+)?")


def cache_path(root: str, filename: str) -> str:
    return os.path.join(root, "testdata", filename)


def load_cache(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(path: str, cache: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def load_manifest(mdir: str) -> list:
    """Load mdir/manifest.json: a list of {"wav", "lang", "ref"} entries."""
    with open(os.path.join(mdir, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def normalize_ja(text: str) -> str:
    """NFKC-normalize Japanese and remove punctuation and whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = _PUNCT_RE.sub("", text)
    return re.sub(r"\s+", "", text)


@dataclass(frozen=True)
class EditCounts:
    substitutions: int
    deletions: int
    insertions: int
    reference_length: int
    leading_deletion: bool = False
    trailing_deletion: bool = False

    @property
    def distance(self) -> int:
        return self.substitutions + self.deletions + self.insertions

    @property
    def cer(self) -> float:
        if self.reference_length == 0:
            return 0.0 if self.distance == 0 else 1.0
        return self.distance / self.reference_length


def edit_counts(reference: str, hypothesis: str, *, normalize: bool = True) -> EditCounts:
    """Return character edit counts and boundary-deletion flags.

    Boundary flags indicate that an optimal alignment starts or ends with a
    deletion from the reference.  They are intentionally conservative: a
    substitution at the first or last character is not called a missing edge.
    """
    ref = normalize_ja(reference) if normalize else reference
    hyp = normalize_ja(hypothesis) if normalize else hypothesis
    rows = len(ref) + 1
    cols = len(hyp) + 1
    costs = [[0] * cols for _ in range(rows)]
    backs: list[list[str]] = [[""] * cols for _ in range(rows)]
    for i in range(1, rows):
        costs[i][0] = i
        backs[i][0] = "D"
    for j in range(1, cols):
        costs[0][j] = j
        backs[0][j] = "I"
    for i in range(1, rows):
        for j in range(1, cols):
            if ref[i - 1] == hyp[j - 1]:
                costs[i][j] = costs[i - 1][j - 1]
                backs[i][j] = "M"
                continue
            choices = (
                (costs[i - 1][j - 1] + 1, "S"),
                (costs[i - 1][j] + 1, "D"),
                (costs[i][j - 1] + 1, "I"),
            )
            costs[i][j], backs[i][j] = min(choices, key=lambda item: item[0])

    ops: list[str] = []
    i, j = len(ref), len(hyp)
    while i or j:
        op = backs[i][j]
        ops.append(op)
        if op in ("M", "S"):
            i -= 1
            j -= 1
        elif op == "D":
            i -= 1
        else:
            j -= 1
    ops.reverse()
    return EditCounts(
        substitutions=ops.count("S"),
        deletions=ops.count("D"),
        insertions=ops.count("I"),
        reference_length=len(ref),
        leading_deletion=bool(ops and ops[0] == "D"),
        trailing_deletion=bool(ops and ops[-1] == "D"),
    )


def levenshtein(a: str, b: str) -> int:
    """Compatibility helper used by the older accuracy harness."""
    return edit_counts(a, b, normalize=False).distance


def cer_ja(reference: str, hypothesis: str) -> tuple[float, int, int]:
    counts = edit_counts(reference, hypothesis)
    return counts.cer, counts.distance, counts.reference_length


def extract_digit_runs(text: str) -> list[str]:
    return _DIGIT_RE.findall(unicodedata.normalize("NFKC", text))


def digits_exact(reference: str, hypothesis: str, expected: Iterable[str] | None = None) -> bool:
    wanted = ([unicodedata.normalize("NFKC", str(value)) for value in expected]
              if expected is not None else extract_digit_runs(reference))
    return wanted == extract_digit_runs(hypothesis)


def term_counts(expected_terms: Iterable[str], hypothesis: str,
                vocabulary: Iterable[str] | None = None) -> tuple[int, int, int]:
    """Return term true-positive, false-negative and false-positive counts."""
    expected = {normalize_ja(term) for term in expected_terms if normalize_ja(term)}
    hyp = normalize_ja(hypothesis)
    present = {term for term in expected if term in hyp}
    vocab = ({normalize_ja(term) for term in vocabulary if normalize_ja(term)}
             if vocabulary is not None else expected)
    false_positive = {term for term in vocab - expected if term in hyp}
    return len(present), len(expected - present), len(false_positive)


def abnormal_repetition(text: str) -> bool:
    """Flag obvious ASR loops without treating ordinary doubled words as loops."""
    value = normalize_ja(text)
    if re.search(r"(.)\1{3,}", value):
        return True
    return any(re.search(rf"({size_re})\1\1", value)
               for size_re in (r".{2}", r".{3,8}", r".{9,20}"))


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
