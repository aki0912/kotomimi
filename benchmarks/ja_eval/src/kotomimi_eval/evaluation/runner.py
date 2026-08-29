from __future__ import annotations

from datetime import datetime, timezone
import os
import platform
from pathlib import Path
import subprocess
import sys

import psutil

from ..errors import DatasetPreparationError
from ..hashing import sha256_file
from ..licensing.registry import DatasetRegistry
from ..licensing.attribution import attribution_requirement
from ..prepare.manifest import load_manifest, write_jsonl_atomic
from ..prepare.suite import suite_paths, verify_suite
from ..prepare.text import normalize_reference_standard
from ..reporting.json_report import write_report_json
from ..reporting.markdown_report import render_report_markdown
from ..suites import SuiteRecord
from .hayamimi_adapter import HayamimiAdapter
from .metrics import aggregate_rows, edit_counts, group_metrics


def _git_commit(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root,
        capture_output=True, text=True, check=False, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _git_dirty(repo_root: Path) -> bool:
    result = subprocess.run(
        ["git", "diff-index", "--quiet", "HEAD", "--"], cwd=repo_root,
        capture_output=True, check=False, timeout=10)
    return result.returncode != 0


def _peak_rss_bytes(process: psutil.Process) -> int:
    try:
        import resource
        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value if sys.platform == "darwin" else value * 1024
    except (ImportError, OSError, ValueError):
        return process.memory_info().rss


def evaluate_suite(
    *,
    suite: SuiteRecord,
    registry: DatasetRegistry,
    data_root: str | Path,
    artifact_root: str | Path,
    threads: int,
    punctuate: bool,
) -> tuple[dict, Path]:
    data_root_path = Path(data_root)
    artifact_root_path = Path(artifact_root)
    suite_manifest, suite_lock = suite_paths(data_root_path, suite.name)
    lock = verify_suite(suite, data_root_path)
    manifest_rows = load_manifest(suite_manifest)
    adapter = HayamimiAdapter(threads=threads, punctuate=punctuate)
    process = psutil.Process(os.getpid())
    scored_rows = []
    for row in manifest_rows:
        record = registry.get(row["dataset_id"])
        audio_path = data_root_path / "prepared" / row["dataset_id"] / record.version / row["audio_path"]
        failure = None
        try:
            hypothesis = adapter.transcribe_file(audio_path)
            text = hypothesis["text"]
            latency_ms = hypothesis["latency_ms"]
            lang = hypothesis["lang"]
            tier = hypothesis["tier"]
        except Exception as exc:
            text, latency_ms, lang, tier = "", 0.0, "", ""
            failure = f"{type(exc).__name__}: {str(exc)[:300]}"
        raw = edit_counts(row["reference_raw"], text, normalize=False)
        hypothesis_eval = normalize_reference_standard(text)
        normalized = edit_counts(row["reference_eval"], hypothesis_eval, normalize=False)
        scored_rows.append({
            "schema_version": 1,
            "sample_id": row["sample_id"],
            "dataset_id": row["dataset_id"],
            "reference_raw": row["reference_raw"],
            "reference_eval": row["reference_eval"],
            "hypothesis_raw": text,
            "hypothesis_eval": hypothesis_eval,
            "lang": lang,
            "tier": tier,
            "audio_s": row["duration_s"],
            "latency_ms": latency_ms,
            "rss_bytes": _peak_rss_bytes(process),
            "sentence_exact": row["reference_eval"] == hypothesis_eval,
            "raw_substitutions": raw.substitutions,
            "raw_deletions": raw.deletions,
            "raw_insertions": raw.insertions,
            "raw_reference_chars": raw.reference_chars,
            "normalized_substitutions": normalized.substitutions,
            "normalized_deletions": normalized.deletions,
            "normalized_insertions": normalized.insertions,
            "normalized_reference_chars": normalized.reference_chars,
            "categories": row["categories"],
            "metadata": row["metadata"],
            "qc_flags": row["qc"]["flags"],
            "failure": failure,
        })
    overall = aggregate_rows(scored_rows)
    by_dataset = group_metrics(scored_rows, lambda row: row["dataset_id"])
    by_duration = group_metrics(
        scored_rows,
        lambda row: "short" if row["audio_s"] < 3 else "medium" if row["audio_s"] <= 8 else "long")
    by_gender = group_metrics(
        scored_rows, lambda row: str(row["metadata"].get("gender") or "unknown"))
    by_digits = group_metrics(
        scored_rows,
        lambda row: ("digit-containing" if any(char.isascii() and char.isdigit()
                                                for char in row["reference_raw"])
                     else "no-ascii-digits"))
    by_latin = group_metrics(
        scored_rows,
        lambda row: ("latin-containing" if any(char.isascii() and char.isalpha()
                                                for char in row["reference_raw"])
                     else "no-latin"))
    by_qc = group_metrics(
        scored_rows, lambda row: "flagged" if row["qc_flags"] else "unflagged")
    dataset_macro = (
        sum(item["normalized"]["cer"] for item in by_dataset.values()) / len(by_dataset)
        if by_dataset else 0.0)
    timestamp = datetime.now(timezone.utc)
    repo_root = Path(__file__).resolve().parents[5]
    commit = _git_commit(repo_root)
    data_provenance = {}
    for dataset_id, dataset_lock in lock["datasets"].items():
        record = registry.get(dataset_id)
        prepared_lock = (data_root_path / "prepared" / dataset_id / record.version
                         / "dataset.lock.json")
        data_provenance[dataset_id] = {
            "version": record.version,
            "source_revision": record.raw.get("source_revision"),
            "source_split": record.source_split,
            "license_spdx": record.license.spdx,
            "license_policy": record.license.policy,
            "prepared_lock_sha256": sha256_file(prepared_lock),
            "prepared_manifest_sha256": dataset_lock["manifest_sha256"],
            "selected_count": dataset_lock["selected_count"],
            "audit_status": "not-run",
            "attribution": attribution_requirement(record),
        }
    run_id = f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-hayamimi-ja-{commit[:8]}"
    run_dir = artifact_root_path / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    hypotheses_path = run_dir / "hypotheses.jsonl"
    _, hypotheses_hash = write_jsonl_atomic(hypotheses_path, scored_rows)
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "suite": {
            "name": suite.name,
            "version": suite.version,
            "lock_sha256": sha256_file(suite_lock),
            "manifest_sha256": lock["manifest_sha256"],
        },
        "system": {
            "id": adapter.system_id,
            "git_commit": commit,
            "git_dirty": _git_dirty(repo_root),
            "forced_lang": "ja",
            "punctuate": punctuate,
            "model_files": adapter.model_hashes(),
        },
        "environment": {
            "os": platform.system(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "threads": threads,
        },
        "metrics": {
            "normalized_micro_cer": overall["normalized"]["cer"],
            "raw_micro_cer": overall["raw"]["cer"],
            "dataset_macro_cer": dataset_macro,
            "sentence_exact_rate": overall["sentence_exact_rate"],
            "substitutions": overall["normalized"]["substitutions"],
            "deletions": overall["normalized"]["deletions"],
            "insertions": overall["normalized"]["insertions"],
            "reference_chars": overall["normalized"]["reference_chars"],
            "decode_failures": overall["decode_failures"],
            "rtf": overall["rtf"],
            "p50_latency_ms": overall["latency_ms_p50"],
            "p95_latency_ms": overall["latency_ms_p95"],
            "peak_rss_bytes": overall["peak_rss_bytes"],
        },
        "datasets": by_dataset,
        "data_provenance": data_provenance,
        "subsets": {
            "duration": by_duration,
            "gender": by_gender,
            "digits": by_digits,
            "latin": by_latin,
            "qc": by_qc,
        },
        "qc": {"view": "official", "flagged_samples": sum(bool(row["qc_flags"]) for row in scored_rows)},
        "artifacts": {"hypotheses_sha256": hypotheses_hash},
        "failures": [
            {"sample_id": row["sample_id"], "error": row["failure"]}
            for row in scored_rows if row["failure"]
        ],
    }
    write_report_json(run_dir / "report.json", report)
    (run_dir / "report.md").write_text(
        render_report_markdown(report), encoding="utf-8", newline="\n")
    return report, run_dir
