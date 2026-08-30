from __future__ import annotations


def _percent(value: float) -> str:
    return f"{100 * value:.2f}%"


def render_report_markdown(report: dict) -> str:
    metrics = report["metrics"]
    status = "PASS" if not report["failures"] else "FAIL"
    gate = "ELIGIBLE" if report["suite"]["release_gate_eligible"] else "NOT ELIGIBLE"
    lines = [
        "# Kotomimi Japanese ASR Evaluation",
        "",
        f"- Execution: **{status}**",
        f"- Release gate: **{gate}**",
        f"- Suite: `{report['suite']['name']}` v{report['suite']['version']}",
        f"- Purpose: `{report['suite']['purpose']}`",
        f"- Quality status: `{report['suite']['quality_status']}`",
        f"- System: `{report['system']['id']}`",
        f"- Git commit: `{report['system']['git_commit']}`",
        f"- Git worktree dirty: `{str(report['system'].get('git_dirty', False)).lower()}`",
        f"- Punctuation: `{'on' if report['system']['punctuate'] else 'off'}`",
        f"- QC view: `{report['qc']['view']}`",
        "",
        "## Overall",
        "",
        "| normalized CER | raw CER | S / D / I | exact | RTF | p50 / p95 ms | peak RSS MiB | failures |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {_percent(metrics['normalized_micro_cer'])} | {_percent(metrics['raw_micro_cer'])} | "
        f"{metrics['substitutions']} / {metrics['deletions']} / {metrics['insertions']} | "
        f"{_percent(metrics['sentence_exact_rate'])} | {metrics['rtf']:.4f} | "
        f"{metrics['p50_latency_ms']:.1f} / {metrics['p95_latency_ms']:.1f} | "
        f"{metrics['peak_rss_bytes'] / 1024 / 1024:.1f} | {metrics['decode_failures']} |",
        "",
        f"Dataset macro CER: **{_percent(metrics['dataset_macro_cer'])}**",
        "",
        "## Datasets",
        "",
        "| dataset | samples | normalized CER | raw CER | S / D / I |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, item in report["datasets"].items():
        lines.append(
            f"| {name} | {item['samples']} | {_percent(item['normalized']['cer'])} | "
            f"{_percent(item['raw']['cer'])} | {item['normalized']['substitutions']} / "
            f"{item['normalized']['deletions']} / {item['normalized']['insertions']} |")
    lines.extend(["", "## Dataset provenance", "",
                  "| dataset | version / revision | split | view | license / policy | selected | audit |",
                  "|---|---|---|---|---|---:|---|"])
    for name, item in report.get("data_provenance", {}).items():
        revision = item.get("source_revision") or item["version"]
        lines.append(
            f"| {name} | `{revision}` | {item['source_split']} | {item.get('source_view', 'prepared')} | "
            f"{item['license_spdx']} / {item['license_policy']} | "
            f"{item['selected_count']} | {item['audit_status']} |")
    lines.extend(["", "## Attribution", ""])
    for name, item in report.get("data_provenance", {}).items():
        attribution = item.get("attribution", {})
        if attribution:
            lines.append(
                f"- {attribution['title']} — {attribution['creator']}; "
                f"{attribution['spdx']}; {attribution['source_url']}")
    view = report["qc"]["view"]
    if view == "official":
        view_note = "Official retains every evaluable clip and is experimental, not a release gate."
    elif view == "clean":
        view_note = "Clean is selected only by pre-ASR QC rules and remains a candidate until re-audited."
    elif view == "stress":
        view_note = "Stress contains QC-excluded clips and must not be presented as representative accuracy."
    else:
        view_note = "Functional results verify execution only and are not accuracy claims."
    lines.extend([
        "",
        "## Reproducibility",
        "",
        f"- Suite lock SHA-256: `{report['suite']['lock_sha256']}`",
        f"- Suite manifest SHA-256: `{report['suite']['manifest_sha256']}`",
        f"- Threads: {report['environment']['threads']}",
        f"- Platform: {report['environment']['platform']}",
        "",
        view_note,
        "Peak RSS is process-wide and includes the loaded ASR model.",
        "",
    ])
    return "\n".join(lines)
