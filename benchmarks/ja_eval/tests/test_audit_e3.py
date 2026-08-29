import re
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler, urlopen

import pytest

from kotomimi_eval.audit.server import create_audit_server
from kotomimi_eval.audit.workflow import (
    append_decision,
    create_audit,
    deterministic_audit_sample,
    load_audit,
    load_audit_status,
    load_decisions,
)
from kotomimi_eval.errors import EvaluationConfigError
from kotomimi_eval.errors import DatasetPreparationError
from kotomimi_eval.licensing.registry import load_registry
from kotomimi_eval.qc.runner import run_qc

from test_qc_e3 import make_prepared_fixture


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _create_fixture_audit(tmp_path, count=4):
    record, _ = make_prepared_fixture(tmp_path, count=6)
    run_qc(record, tmp_path / "data", tmp_path / "artifacts")
    metadata, directory = create_audit(
        record, tmp_path / "data", tmp_path / "artifacts", count=count, seed=20260829)
    return record, metadata, directory


def test_audit_sample_is_deterministic_and_idempotent(tmp_path):
    record, rows = make_prepared_fixture(tmp_path, count=6)
    first = deterministic_audit_sample(record, rows, 4, 20260829)
    second = deterministic_audit_sample(record, list(reversed(rows)), 4, 20260829)
    assert [row["sample_id"] for row in first] == [row["sample_id"] for row in second]
    run_qc(record, tmp_path / "data", tmp_path / "artifacts")
    metadata, directory = create_audit(
        record, tmp_path / "data", tmp_path / "artifacts", count=4, seed=20260829)
    repeated, repeated_directory = create_audit(
        record, tmp_path / "data", tmp_path / "artifacts", count=4, seed=20260829)
    assert repeated["samples_sha256"] == metadata["samples_sha256"]
    assert repeated_directory == directory


def test_decisions_append_history_and_compute_gate_status(tmp_path):
    _, metadata, _ = _create_fixture_audit(tmp_path, count=2)
    _, samples, _ = load_audit(tmp_path / "artifacts", metadata["audit_id"])
    sample_ids = {row["sample_id"] for row in samples}
    for row in samples:
        append_decision(tmp_path / "artifacts", metadata["audit_id"], sample_ids, {
            "sample_id": row["sample_id"],
            "label": "ok",
            "noise_level": "clean",
            "speech_style": "read",
        })
    append_decision(tmp_path / "artifacts", metadata["audit_id"], sample_ids, {
        "sample_id": samples[0]["sample_id"],
        "label": "minor_transcript_issue",
        "noise_level": "mild",
        "speech_style": "read",
        "reviewer_comment": "second decision remains in history",
    })
    history, latest = load_decisions(tmp_path / "artifacts", metadata["audit_id"])
    assert len(history) == 3
    assert latest[samples[0]["sample_id"]]["label"] == "minor_transcript_issue"
    status = load_audit_status(tmp_path / "artifacts", metadata["audit_id"])
    assert status["complete"] is True
    assert status["approved_for_gate"] is True


def test_audit_server_persists_post_and_shuts_down(tmp_path):
    _, metadata, _ = _create_fixture_audit(tmp_path, count=2)
    server = create_audit_server(
        audit_id=metadata["audit_id"], registry=load_registry(),
        data_root=tmp_path / "data", artifact_root=tmp_path / "artifacts",
        host="127.0.0.1", port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        page = urlopen(base + "/", timeout=5).read().decode()
        assert "raw-client" not in page
        csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
        sample_id = re.search(r'name="sample_id" value="([a-f0-9]{64})"', page).group(1)
        audio = urlopen(base + f"/audio/{sample_id}", timeout=5)
        assert audio.headers["Content-Type"] == "audio/flac"
        payload = urlencode({
            "csrf": csrf,
            "sample_id": sample_id,
            "position": "0",
            "filter": "all",
            "label": "ok",
            "noise_level": "clean",
            "speech_style": "read",
            "spoken_text_notes": "",
            "reviewer_comment": "persisted",
        }).encode()
        with pytest.raises(HTTPError) as response:
            build_opener(NoRedirect).open(Request(base + "/decision", data=payload), timeout=5)
        assert response.value.code == 303
        status = load_audit_status(tmp_path / "artifacts", metadata["audit_id"])
        assert status["reviewed"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert not thread.is_alive()


def test_audit_server_rejects_external_bind(tmp_path):
    _, metadata, _ = _create_fixture_audit(tmp_path, count=2)
    with pytest.raises(EvaluationConfigError, match="loopback"):
        create_audit_server(
            audit_id=metadata["audit_id"], registry=load_registry(),
            data_root=tmp_path / "data", artifact_root=tmp_path / "artifacts",
            host="0.0.0.0", port=0,
        )


def test_concurrent_decisions_are_complete_jsonl_records(tmp_path):
    _, metadata, _ = _create_fixture_audit(tmp_path, count=4)
    _, samples, directory = load_audit(tmp_path / "artifacts", metadata["audit_id"])
    sample_ids = {row["sample_id"] for row in samples}

    def write(index):
        row = samples[index % len(samples)]
        return append_decision(tmp_path / "artifacts", metadata["audit_id"], sample_ids, {
            "sample_id": row["sample_id"],
            "label": "ok",
            "noise_level": "clean",
            "speech_style": "read",
            "reviewer_comment": f"decision-{index}",
        })

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write, range(40)))
    history, latest = load_decisions(tmp_path / "artifacts", metadata["audit_id"])
    assert len(history) == 40
    assert len(latest) == 4
    assert len((directory / "decisions.jsonl").read_text().splitlines()) == 40


def test_incomplete_decision_line_fails_closed(tmp_path):
    _, metadata, directory = _create_fixture_audit(tmp_path, count=2)
    (directory / "decisions.jsonl").write_text('{"incomplete":', encoding="utf-8")
    with pytest.raises(DatasetPreparationError, match="incomplete"):
        load_decisions(tmp_path / "artifacts", metadata["audit_id"])
