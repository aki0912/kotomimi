from kotomimi_eval.reporting.markdown_report import render_report_markdown


def test_markdown_report_states_conditions_and_metrics():
    report = {
        "failures": [],
        "suite": {"name": "minimum-fleurs", "version": 1,
                  "lock_sha256": "a" * 64, "manifest_sha256": "b" * 64,
                  "purpose": "official_regression", "quality_status": "experimental",
                  "evaluation_view": "official", "release_gate_eligible": False},
        "system": {"id": "hayamimi-ja", "git_commit": "deadbeef", "punctuate": False},
        "environment": {"threads": 4, "platform": "test-platform"},
        "qc": {"view": "official"},
        "metrics": {
            "normalized_micro_cer": 0.1, "raw_micro_cer": 0.2,
            "substitutions": 1, "deletions": 2, "insertions": 3,
            "sentence_exact_rate": 0.5, "rtf": 0.01,
            "p50_latency_ms": 10.0, "p95_latency_ms": 20.0,
            "peak_rss_bytes": 1048576, "decode_failures": 0,
            "dataset_macro_cer": 0.1,
        },
        "datasets": {
            "fleurs_ja": {"samples": 2, "normalized": {"cer": 0.1, "substitutions": 1,
                            "deletions": 2, "insertions": 3}, "raw": {"cer": 0.2}}
        },
        "data_provenance": {
            "fleurs_ja": {"version": "rev", "source_revision": "rev", "source_split": "test",
                           "license_spdx": "CC-BY-4.0", "license_policy": "strict",
                           "selected_count": 2, "audit_status": "not-run",
                           "attribution": {"title": "FLEURS", "creator": "Google",
                                           "spdx": "CC-BY-4.0",
                                           "source_url": "https://example.test/fleurs"}}
        },
    }
    text = render_report_markdown(report)
    assert "normalized CER" in text
    assert "official" in text
    assert "Punctuation: `off`" in text
    assert "Suite lock SHA-256" in text
    assert "CC-BY-4.0 / strict" in text
    assert "FLEURS — Google" in text
