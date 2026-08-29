"""Conservative suffix/prefix merging for overlapping ASR audio windows."""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata


@dataclass(frozen=True)
class MergeResult:
    merged_text: str
    current_delta: str
    matched_previous_suffix: str
    matched_current_prefix: str
    similarity: float
    applied: bool


def _comparison_text_with_map(text: str) -> tuple[str, list[tuple[int, int]]]:
    normalized: list[str] = []
    source_spans: list[tuple[int, int]] = []
    source_index = 0
    while source_index < len(text):
        cluster_end = source_index + 1
        while cluster_end < len(text) and (
                unicodedata.combining(text[cluster_end])
                or text[cluster_end] in {"ﾞ", "ﾟ"}):
            cluster_end += 1
        cluster = text[source_index:cluster_end]
        for char in unicodedata.normalize("NFKC", cluster).casefold():
            if char.isspace() or unicodedata.category(char).startswith("P"):
                continue
            normalized.append(char)
            source_spans.append((source_index, cluster_end))
        source_index = cluster_end
    return "".join(normalized), source_spans


def _edit_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for row, lchar in enumerate(left, start=1):
        current = [row]
        for column, rchar in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (lchar != rchar),
            ))
        previous = current
    return previous[-1]


def _similarity(left: str, right: str) -> float:
    size = max(len(left), len(right))
    return 1.0 if size == 0 else 1.0 - _edit_distance(left, right) / size


def _extend_over_ignored_prefix(text: str, end: int) -> int:
    while end < len(text):
        normalized = unicodedata.normalize("NFKC", text[end])
        if normalized and not all(
                char.isspace() or unicodedata.category(char).startswith("P")
                for char in normalized):
            break
        end += 1
    return end


def _unchanged(previous: str, current: str) -> MergeResult:
    return MergeResult(
        merged_text=previous + current,
        current_delta=current,
        matched_previous_suffix="",
        matched_current_prefix="",
        similarity=0.0,
        applied=False,
    )


def _looks_like_deliberate_repetition(text: str) -> bool:
    if len(text) < 4:
        return False
    for unit_length in range(1, len(text) // 2 + 1):
        if len(text) % unit_length == 0:
            unit = text[:unit_length]
            if unit * (len(text) // unit_length) == text:
                return True
    return False


def merge_overlapping_text(
    previous: str,
    current: str,
    *,
    audio_overlap_s: float,
    min_overlap_chars: int = 2,
    max_overlap_chars: int = 40,
    min_similarity: float = 0.82,
) -> MergeResult:
    """Merge a prior suffix with a current prefix only when audio overlaps.

    Comparison uses NFKC, punctuation/space removal, and case folding, while
    returned strings retain the caller's original spelling and punctuation.
    """
    if audio_overlap_s <= 0 or not previous or not current:
        return _unchanged(previous, current)
    if min_overlap_chars < 1 or max_overlap_chars < min_overlap_chars:
        raise ValueError("invalid overlap character bounds")
    if not 0 <= min_similarity <= 1:
        raise ValueError("min_similarity must be between 0 and 1")

    previous_norm, previous_map = _comparison_text_with_map(previous)
    current_norm, current_map = _comparison_text_with_map(current)
    available = min(max_overlap_chars, len(previous_norm), len(current_norm))
    if available < min_overlap_chars:
        return _unchanged(previous, current)

    best: tuple[int, int, float] | None = None
    best_key: tuple[int, int, float] | None = None
    # Permit a small insertion/deletion around the boundary, but prefer the
    # candidate consuming the most characters and then the highest score.
    for previous_length in range(available, min_overlap_chars - 1, -1):
        lower = max(min_overlap_chars, previous_length - 2)
        upper = min(available, previous_length + 2)
        for current_length in range(upper, lower - 1, -1):
            left = previous_norm[-previous_length:]
            right = current_norm[:current_length]
            similarity = _similarity(left, right)
            if similarity < min_similarity:
                continue
            overlap_text = left + right
            # Digits and Latin product identifiers are too costly to merge
            # fuzzily: one changed character may be a different version or
            # quantity rather than an ASR error.
            if any(char.isascii() and char.isalnum() for char in overlap_text) \
                    and similarity < 1.0:
                continue
            matched_size = min(previous_length, current_length)
            candidate = (matched_size, previous_length + current_length, similarity)
            if best_key is None or candidate > best_key:
                best = (previous_length, current_length, similarity)
                best_key = candidate

    if best is None:
        return _unchanged(previous, current)
    previous_length, current_length, similarity = best
    match_length = min(previous_length, current_length)
    matched_previous_norm = previous_norm[-previous_length:]

    # Short acknowledgements and explicit repetitions carry meaning.  Their
    # removal is riskier than the small boundary cleanup they could provide.
    if matched_previous_norm in {"はい", "そう", "うん", "ええ"}:
        return _unchanged(previous, current)
    if previous_length == len(previous_norm) \
            and _looks_like_deliberate_repetition(previous_norm):
        return _unchanged(previous, current)

    # Short Japanese acknowledgements are frequently legitimate repetitions.
    # Never consume a prior utterance consisting only of 2-3 characters, and
    # require substantial audio overlap for any other short match.
    if match_length <= 3:
        if len(previous_norm) <= 3:
            return _unchanged(previous, current)
        required_audio = 0.8 if match_length == 2 else 0.5
        if similarity < 1.0 or audio_overlap_s < required_audio:
            return _unchanged(previous, current)

    # A complete duplicate window is plausible only with long audio overlap;
    # otherwise keep it rather than deleting a repeated utterance.
    if current_length == len(current_norm) and audio_overlap_s < 0.8:
        return _unchanged(previous, current)

    previous_start = previous_map[len(previous_norm) - previous_length][0]
    current_end = current_map[current_length - 1][1]
    previous_semantic_end = previous_map[-1][1]
    previous_trailing = previous[previous_semantic_end:]
    if any(unicodedata.category(char).startswith("P") for char in previous_trailing):
        current_end = _extend_over_ignored_prefix(current, current_end)
    delta = current[current_end:]
    return MergeResult(
        merged_text=previous + delta,
        current_delta=delta,
        matched_previous_suffix=previous[previous_start:],
        matched_current_prefix=current[:current_end],
        similarity=similarity,
        applied=True,
    )
