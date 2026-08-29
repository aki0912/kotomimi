from collections import Counter

from kotomimi_eval.prepare.sampling import (
    deterministic_common_voice_sample,
    deterministic_stratified_sample,
)


def _rows():
    return [
        {
            "sample_id": f"{index:064x}",
            "duration_s": 2.0 if index % 3 == 0 else 5.0 if index % 3 == 1 else 9.0,
            "metadata": {"gender": "female" if index % 5 == 0 else "male"},
        }
        for index in range(100)
    ]


def test_sampling_is_stable_and_not_first_n():
    rows = _rows()
    first = deterministic_stratified_sample(rows, 30, 20260829)
    second = deterministic_stratified_sample(list(reversed(rows)), 30, 20260829)
    assert [row["sample_id"] for row in first] == [row["sample_id"] for row in second]
    assert {row["sample_id"] for row in first} != {row["sample_id"] for row in rows[:30]}


def test_sampling_preserves_strata_proportion_with_rounding():
    selected = deterministic_stratified_sample(_rows(), 50, 20260829)
    genders = Counter(row["metadata"]["gender"] for row in selected)
    # Quotas are allocated over gender x duration strata, so the marginal
    # gender total can differ by one after per-stratum largest remainders.
    assert abs(genders["male"] - 40) <= 1
    assert abs(genders["female"] - 10) <= 1


def _common_voice_rows():
    rows = []
    for index in range(2000):
        rows.append({
            "sample_id": f"{index:064x}",
            "speaker_id": f"speaker-{index % 400}",
            "duration_s": 2.0 if index % 3 == 0 else 5.0 if index % 3 == 1 else 9.0,
            "metadata": {
                "vote_margin_bin": ("one", "two_to_three", "four_plus")[index % 3],
                "sentence_domain": ("general", "news")[index % 2],
                "age": ("twenties", "thirties", "unknown")[index % 3],
                "gender": ("female", "male")[index % 2],
            },
        })
    return rows


def test_common_voice_sampling_is_deterministic_and_speaker_aware():
    rows = _common_voice_rows()
    first = deterministic_common_voice_sample(rows, 1000, 20260829)
    second = deterministic_common_voice_sample(list(reversed(rows)), 1000, 20260829)
    assert [row["sample_id"] for row in first] == [row["sample_id"] for row in second]
    speaker_counts = Counter(row["speaker_id"] for row in first)
    assert max(speaker_counts.values()) <= 3
    assert len(speaker_counts) >= 390


def test_common_voice_sampling_preserves_metadata_strata():
    selected = deterministic_common_voice_sample(_common_voice_rows(), 1000, 20260829)
    source_domains = Counter(row["metadata"]["sentence_domain"] for row in _common_voice_rows())
    selected_domains = Counter(row["metadata"]["sentence_domain"] for row in selected)
    assert selected_domains["general"] == source_domains["general"] // 2
    assert selected_domains["news"] == source_domains["news"] // 2
