import pytest

from kotomimi_eval.errors import LicensePolicyError
from kotomimi_eval.licensing.registry import load_registry
from kotomimi_eval.suites import load_suites, validate_suite_licenses


def test_strict_suites_contain_only_strict_datasets():
    registry = load_registry()
    suites = load_suites()
    for name in ("smoke", "minimum-fleurs", "minimum-strict", "minimum-strict-spreds", "standard-strict"):
        validate_suite_licenses(suites[name], registry)


def test_extended_suite_requires_sharealike_opt_in():
    registry = load_registry()
    suite = load_suites()["minimum-extended"]
    with pytest.raises(LicensePolicyError, match="opt-in"):
        validate_suite_licenses(suite, registry)
    validate_suite_licenses(suite, registry, allow_sharealike=True)


def test_jnv_is_explicitly_nonverbal_not_cer():
    for name in ("minimum-extended", "standard-extended"):
        assert load_suites()[name].datasets["jnv"]["metric_family"] == "nonverbal"


def test_policy_profiles_are_explicit_and_never_release_gates():
    suites = load_suites()
    expected = {
        "official-experimental": ("official_regression", "experimental", "official"),
        "fleurs-clean-candidate": ("clean_candidate", "candidate", "clean"),
        "quality-stress": ("quality_stress", "experimental", "stress"),
    }
    for name, metadata in expected.items():
        suite = suites[name]
        assert (suite.purpose, suite.quality_status, suite.evaluation_view) == metadata
        assert suite.release_gate_eligible is False
