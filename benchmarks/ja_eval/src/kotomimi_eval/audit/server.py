from __future__ import annotations

from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import parse_qs, quote, urlparse

from ..errors import EvaluationConfigError
from ..hashing import sha256_file
from ..licensing.registry import DatasetRegistry
from ..paths import safe_relative_parts
from .workflow import (
    AUDIT_LABELS,
    NOISE_LEVELS,
    SPEECH_STYLES,
    append_decision,
    load_audit,
    load_audit_status,
    load_decisions,
)


def _options(values: tuple[str, ...], selected: str) -> str:
    options = []
    for value in values:
        selected_attribute = " selected" if value == selected else ""
        options.append(
            f'<option value="{escape(value)}"{selected_attribute}>{escape(value)}</option>')
    return "".join(options)


def _page(
    metadata: dict,
    samples: list[dict],
    latest: dict[str, dict],
    *,
    position: int,
    filter_name: str,
    csrf_token: str,
) -> str:
    if filter_name == "unreviewed":
        visible = [index for index, row in enumerate(samples) if row["sample_id"] not in latest]
    elif filter_name == "review":
        visible = [
            index for index, row in enumerate(samples)
            if latest.get(row["sample_id"], {}).get("label") == "uncertain"
        ]
    else:
        filter_name = "all"
        visible = list(range(len(samples)))
    status = load_audit_status(metadata["artifact_root"], metadata["audit_id"])
    if not visible:
        return f"""<!doctype html><html><head><meta charset="utf-8"><title>Audit complete</title></head>
<body><h1>{escape(metadata['audit_id'])}</h1><p>No samples match this filter.</p>
<p>Reviewed {status['reviewed']} / {status['total']}</p><a href="/?filter=all">Show all</a></body></html>"""
    position = max(0, min(position, len(visible) - 1))
    row = samples[visible[position]]
    decision = latest.get(row["sample_id"], {})
    label = decision.get("label", "ok")
    noise = decision.get("noise_level", "clean")
    style = decision.get("speech_style", "read")
    labels = "".join(
        f'<label><input type="radio" name="label" value="{escape(value)}" '
        f"{'checked' if value == label else ''}> [{index}] {escape(value)}</label>"
        for index, value in enumerate(AUDIT_LABELS, start=1)
    )
    previous_position = max(0, position - 1)
    next_position = min(len(visible) - 1, position + 1)
    flags = ", ".join(row.get("qc", {}).get("flags", [])) or "none"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>{escape(metadata['audit_id'])}</title>
<style>body{{font:16px system-ui;max-width:1000px;margin:1rem auto;padding:0 1rem;color:#17202a}}
nav,.progress{{display:flex;gap:1rem;flex-wrap:wrap;margin:.8rem 0}}audio{{width:100%}}
.labels{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:.4rem}}
label{{display:block}}textarea{{width:100%;min-height:4rem}}code{{overflow-wrap:anywhere}}
button{{font-size:1rem;padding:.6rem 1.2rem}}.reference{{font-size:1.25rem;background:#f3f5f7;padding:1rem}}
</style></head><body><h1>{escape(metadata['audit_id'])}</h1>
<div class="progress"><strong>Filtered {position + 1}/{len(visible)}</strong>
<span>Reviewed {status['reviewed']}/{status['total']}</span><span>Remaining {status['remaining']}</span></div>
<nav><a id="prev" href="/?filter={filter_name}&position={previous_position}">← Previous</a>
<a id="next" href="/?filter={filter_name}&position={next_position}">Next →</a>
<a href="/?filter=all">All</a><a href="/?filter=unreviewed">Unreviewed</a>
<a href="/?filter=review">Needs review</a></nav>
<audio controls preload="metadata" src="/audio/{row['sample_id']}"></audio>
<p class="reference"><strong>Raw:</strong> {escape(row['reference_raw'])}<br>
<strong>Normalized:</strong> {escape(row['reference_eval'])}</p>
<p>Dataset: <code>{escape(row['dataset_id'])}</code> · Sample: <code>{row['sample_id']}</code><br>
Duration: {row['duration_s']:.3f}s · QC: {escape(flags)}</p>
<form method="post" action="/decision" id="decision"><input type="hidden" name="csrf" value="{csrf_token}">
<input type="hidden" name="sample_id" value="{row['sample_id']}">
<input type="hidden" name="position" value="{position}"><input type="hidden" name="filter" value="{filter_name}">
<fieldset><legend>Decision (keys 1–9)</legend><div class="labels">{labels}</div></fieldset>
<label>Noise <select name="noise_level">{_options(NOISE_LEVELS, noise)}</select></label>
<label>Speech style <select name="speech_style">{_options(SPEECH_STYLES, style)}</select></label>
<label>Spoken text notes<textarea name="spoken_text_notes">{escape(decision.get('spoken_text_notes', ''))}</textarea></label>
<label>Reviewer comment<textarea name="reviewer_comment">{escape(decision.get('reviewer_comment', ''))}</textarea></label>
<button type="submit">Save decision</button></form>
<script>document.addEventListener('keydown',e=>{{if(e.target.matches('textarea,input,select'))return;
if(e.key==='ArrowLeft')document.getElementById('prev').click();if(e.key==='ArrowRight')document.getElementById('next').click();
let n=Number(e.key);if(n>=1&&n<=9)document.querySelectorAll('input[name=label]')[n-1].click();}});</script>
</body></html>"""


def create_audit_server(
    *,
    audit_id: str,
    registry: DatasetRegistry,
    data_root: str | Path,
    artifact_root: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost"}:
        raise EvaluationConfigError("audit server only permits a loopback host")
    metadata, samples, _ = load_audit(artifact_root, audit_id)
    record = registry.get(metadata["dataset_id"])
    prepared = Path(data_root) / "prepared" / record.dataset_id / record.version
    sample_by_id = {row["sample_id"]: row for row in samples}
    csrf_token = secrets.token_urlsafe(32)
    page_metadata = {**metadata, "artifact_root": str(artifact_root)}

    class Handler(BaseHTTPRequestHandler):
        server_version = "KotomimiAudit/1"

        def log_message(self, format: str, *args) -> None:
            return

        def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src 'self'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                query = parse_qs(parsed.query)
                try:
                    position = int(query.get("position", ["0"])[0])
                except ValueError:
                    position = 0
                filter_name = query.get("filter", ["all"])[0]
                _, latest = load_decisions(artifact_root, audit_id)
                body = _page(
                    page_metadata, samples, latest,
                    position=position, filter_name=filter_name, csrf_token=csrf_token,
                ).encode("utf-8")
                self._send(HTTPStatus.OK, "text/html; charset=utf-8", body)
                return
            if parsed.path.startswith("/audio/"):
                sample_id = parsed.path.removeprefix("/audio/")
                row = sample_by_id.get(sample_id)
                if row is None:
                    self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found\n")
                    return
                try:
                    relative_audio = safe_relative_parts(row["audio_path"])
                except ValueError:
                    self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found\n")
                    return
                audio = prepared.joinpath(*relative_audio)
                try:
                    if (not audio.resolve().is_relative_to(prepared.resolve())
                            or sha256_file(audio) != row["audio_sha256"]):
                        raise OSError("audio integrity check failed")
                    body = audio.read_bytes()
                except OSError:
                    self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found\n")
                    return
                self._send(HTTPStatus.OK, "audio/flac", body)
                return
            if parsed.path == "/status.json":
                body = (json.dumps(load_audit_status(artifact_root, audit_id), ensure_ascii=False,
                                   sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
                self._send(HTTPStatus.OK, "application/json; charset=utf-8", body)
                return
            self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found\n")

        def do_POST(self) -> None:
            if self.path != "/decision":
                self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found\n")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > 32_768:
                self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", b"invalid request\n")
                return
            try:
                values = {key: items[0] for key, items in parse_qs(
                    self.rfile.read(length).decode("utf-8"), keep_blank_values=True).items()}
            except UnicodeDecodeError:
                self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", b"invalid request\n")
                return
            if not secrets.compare_digest(values.pop("csrf", ""), csrf_token):
                self._send(HTTPStatus.FORBIDDEN, "text/plain; charset=utf-8", b"forbidden\n")
                return
            try:
                append_decision(artifact_root, audit_id, set(sample_by_id), values)
                position = int(values.get("position", "0"))
            except (EvaluationConfigError, ValueError):
                self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", b"invalid decision\n")
                return
            filter_name = values.get("filter", "all")
            next_position = position if filter_name == "unreviewed" else position + 1
            location = f"/?filter={quote(filter_name)}&position={next_position}"
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def serve_audit(**kwargs) -> None:
    server = create_audit_server(**kwargs)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
