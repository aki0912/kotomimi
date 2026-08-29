from __future__ import annotations


def _percent(value: float) -> str:
    return f"{100 * value:.2f}%"


def render_report_markdown(report: dict) -> str:
    metrics = report["metrics"]
    status = "PASS" if not report["failures"] else "FAIL"
    lines = [
        "# Kotomimi Japanese ASR Evaluation",
        "",
        f"- Status: **{status}**",
        f"- Suite: `{report['suite']['name']}` v{report['suite']['version']}",
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
                  "| dataset | version / revision | split | license / policy | selected | audit |",
                  "|---|---|---|---|---:|---|"])
    for name, item in report.get("data_provenance", {}).items():
        revision = item.get("source_revision") or item["version"]
        lines.append(
            f"| {name} | `{revision}` | {item['source_split']} | "
            f"{item['license_spdx']} / {item['license_policy']} | "
            f"{item['selected_count']} | {item['audit_status']} |")
    lines.extend(["", "## Attribution", ""])
    for name, item in report.get("data_provenance", {}).items():
        attribution = item.get("attribution", {})
        if attribution:
            lines.append(
                f"- {attribution['title']} — {attribution['creator']}; "
                f"{attribution['spdx']}; {attribution['source_url']}")
    lines.extend([
        "",
        "## Reproducibility",
        "",
        f"- Suite lock SHA-256: `{report['suite']['lock_sha256']}`",
        f"- Suite manifest SHA-256: `{report['suite']['manifest_sha256']}`",
        f"- Threads: {report['environment']['threads']}",
        f"- Platform: {report['environment']['platform']}",
        "",
        "This report uses the official view. QC flags are reported but are not used to remove clips.",
        "Peak RSS is process-wide and includes the loaded ASR model.",
        "",
    ])
    return "\n".join(lines)
