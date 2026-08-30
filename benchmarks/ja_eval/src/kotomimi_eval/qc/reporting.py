from __future__ import annotations

from html import escape


def render_qc_markdown(report: dict) -> str:
    lines = [
        f"# QC report: {report['dataset_id']}",
        "",
        f"- Dataset version: `{report['dataset_version']}`",
        f"- Source split: `{report['source_split']}`",
        f"- Input rows: {report['input_rows']}",
        f"- Official rows: {report['views']['official']['rows']}",
        f"- Clean rows: {report['views']['clean']['rows']}",
        f"- Stress rows: {report['views']['stress']['rows']}",
        f"- Hard failures: {len(report['hard_failures'])}",
        f"- Speech activity method: `{report['speech_activity']['method']}`",
        f"- Speech frame: {report['speech_activity']['frame_ms']} ms",
        f"- Speech threshold: {report['speech_activity']['threshold_dbfs']} dBFS",
        "",
        "The official view retains every evaluable source row. The clean view is a",
        "secondary subset only; it must not replace the official benchmark result.",
        "No ASR hypothesis is used for exclusion.",
        "",
        "## Flag counts",
        "",
        "| flag | count | clean exclusion |",
        "|---|---:|:---:|",
    ]
    excluded = set(report["clean_exclude_flags"])
    for flag, count in report["flag_counts"].items():
        lines.append(f"| `{flag}` | {count} | {'yes' if flag in excluded else 'no'} |")
    if not report["flag_counts"]:
        lines.append("| — | 0 | — |")
    lines.extend([
        "",
        "## Duplicate groups",
        "",
        "| kind | groups | affected rows |",
        "|---|---:|---:|",
    ])
    for kind, item in report["duplicates"].items():
        lines.append(f"| `{kind}` | {item['groups']} | {item['affected_rows']} |")
    if report["hard_failures"]:
        lines.extend(["", "## Hard failures", ""])
        for failure in report["hard_failures"]:
            lines.append(f"- `{failure['sample_id']}`: {failure['error']}")
    return "\n".join(lines) + "\n"


def render_qc_html(report: dict) -> str:
    excluded = set(report["clean_exclude_flags"])
    flag_rows = "".join(
        "<tr><td><code>{}</code></td><td>{}</td><td>{}</td></tr>".format(
            escape(flag), count, "yes" if flag in excluded else "no")
        for flag, count in report["flag_counts"].items()
    ) or '<tr><td colspan="3">No flags</td></tr>'
    duplicate_rows = "".join(
        "<tr><td><code>{}</code></td><td>{}</td><td>{}</td></tr>".format(
            escape(kind), item["groups"], item["affected_rows"])
        for kind, item in report["duplicates"].items()
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>QC report: {escape(report['dataset_id'])}</title>
<style>body{{font:16px system-ui;max-width:960px;margin:2rem auto;padding:0 1rem;color:#18212b}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #ccd3da;padding:.45rem;text-align:left}}
.notice{{background:#fff6d8;border-left:5px solid #d99a00;padding:1rem}}code{{font-size:.9em}}</style></head>
<body><h1>QC report: {escape(report['dataset_id'])}</h1>
<p class="notice">Official retains every evaluable row. Clean is a secondary QC subset only.
No ASR hypothesis is used for exclusion.</p>
<ul><li>Input: {report['input_rows']}</li><li>Official: {report['views']['official']['rows']}</li>
<li>Clean: {report['views']['clean']['rows']}</li><li>Stress: {report['views']['stress']['rows']}</li>
<li>Hard failures: {len(report['hard_failures'])}</li>
<li>Speech activity: <code>{escape(report['speech_activity']['method'])}</code>,
{report['speech_activity']['frame_ms']} ms frames at {report['speech_activity']['threshold_dbfs']} dBFS</li></ul>
<h2>Flags</h2><table><thead><tr><th>Flag</th><th>Count</th><th>Clean exclusion</th></tr></thead>
<tbody>{flag_rows}</tbody></table>
<h2>Duplicate groups</h2><table><thead><tr><th>Kind</th><th>Groups</th><th>Affected rows</th></tr></thead>
<tbody>{duplicate_rows}</tbody></table></body></html>"""
