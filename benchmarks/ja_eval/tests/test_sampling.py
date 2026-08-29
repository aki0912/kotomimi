from collections import Counter

from kotomimi_eval.prepare.sampling import deterministic_stratified_sample


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
