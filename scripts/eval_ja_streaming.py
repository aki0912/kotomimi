#!/usr/bin/env python3
"""Evaluate Japanese offline and VAD paths from one JSONL manifest.

The metric and report helpers in this module do not import ASR libraries.
Model-backed imports occur only after manifest validation and model checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from eval_common import (abnormal_repetition, digits_exact, edit_counts,
                         extract_digit_runs, percentile, term_counts)


ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
DEFAULT_MODES = ("offline_primary", "stream_fast", "stream_refine", "stream_single_ja")
REQUIRED_FIELDS = ("id", "wav", "text", "category")
OPTIONAL_LIST_FIELDS = ("terms", "digits")


class ManifestError(ValueError):
    pass


def load_manifest(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    manifest_path = Path(path)
    entries: list[dict[str, Any]] = []
    ids: set[str] = set()
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ManifestError(f"cannot read manifest: {manifest_path}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"{manifest_path}:{line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(entry, dict):
            raise ManifestError(f"{manifest_path}:{line_number}: each line must be a JSON object")
        missing = [field for field in REQUIRED_FIELDS if field not in entry]
        if missing:
            raise ManifestError(f"{manifest_path}:{line_number}: missing fields: {', '.join(missing)}")
        for field in REQUIRED_FIELDS:
            if not isinstance(entry[field], str) or not entry[field].strip():
                raise ManifestError(f"{manifest_path}:{line_number}: {field} must be a non-empty string")
        if entry["id"] in ids:
            raise ManifestError(f"{manifest_path}:{line_number}: duplicate id: {entry['id']}")
        ids.add(entry["id"])
        for field in OPTIONAL_LIST_FIELDS:
            if field in entry and (not isinstance(entry[field], list)
                                   or not all(isinstance(value, (str, int, float))
                                              for value in entry[field])):
                raise ManifestError(f"{manifest_path}:{line_number}: {field} must be a list")
        wav = Path(entry["wav"])
        entry = dict(entry)
        entry["wav_path"] = str(wav if wav.is_absolute() else manifest_path.parent / wav)
        entries.append(entry)
    if not entries:
        raise ManifestError(f"{manifest_path}: dataset is empty")
    return entries


def model_status() -> tuple[bool, list[str]]:
    reazon = MODELS_DIR / "sherpa-onnx-zipformer-ja-en-reazonspeech-2025-01-17"
    whisper = MODELS_DIR / "sherpa-onnx-whisper-tiny"
    checks = {
        "ReazonSpeech encoder": any(reazon.glob("encoder-*.int8.onnx")),
        "ReazonSpeech decoder": any(reazon.glob("decoder-*.int8.onnx")),
        "ReazonSpeech joiner": any(reazon.glob("joiner-*.int8.onnx")),
        "ReazonSpeech tokens": (reazon / "tokens.txt").is_file(),
        "whisper-tiny LID encoder": (whisper / "tiny-encoder.int8.onnx").is_file(),
        "whisper-tiny LID decoder": (whisper / "tiny-decoder.int8.onnx").is_file(),
        "Silero VAD": (MODELS_DIR / "silero_vad.onnx").is_file(),
    }
    missing = [name for name, present in checks.items() if not present]
    return not missing, missing


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def environment_metadata() -> dict[str, Any]:
    try:
        import sherpa_onnx
        sherpa_version = getattr(sherpa_onnx, "__version__", "unknown")
    except ImportError:
        sherpa_version = None
    model_dirs = sorted(path.name for path in MODELS_DIR.iterdir()) if MODELS_DIR.is_dir() else []
    vad = MODELS_DIR / "silero_vad.onnx"
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "sherpa_onnx": sherpa_version,
        "model_directories": model_dirs,
        "vad_sha256": _file_sha256(vad) if vad.is_file() else None,
    }


@dataclass
class DecodeOutput:
    text: str
    audio_s: float
    decode_ms: float
    final_latencies_ms: list[float]
    max_rss_bytes: int
    segments: int = 1


class _CaptureServer:
    def __init__(self):
        self.finals: list[dict[str, Any]] = []
        self.refines: list[dict[str, Any]] = []

    def final(self, text, lang, speaker, latency_ms, tier):
        self.finals.append({"text": text, "lang": lang, "latency_ms": latency_ms, "tier": tier})

    def publish(self, event):
        if event.get("type") == "refine":
            self.refines.append(dict(event))


def _rss_bytes() -> int:
    try:
        import psutil
        return psutil.Process().memory_info().rss
    except ImportError:
        return 0


class Evaluator:
    """Model-backed evaluator that reuses the production ASR/VAD pipeline."""

    def __init__(self, threads: int, min_silence: float, max_speech: float):
        from asr_engine import RoutedASR

        self.threads = threads
        self.min_silence = min_silence
        self.max_speech = max_speech
        # Match the production CLI: model/LID warmup happens before measured
        # audio, while background preload stays off to keep eval timing stable.
        common = dict(threads=threads, warmup=True, preload=False, max_resident=3)
        self.single_asr = RoutedASR(**common, forced_lang="ja")
        self.balanced_asr = RoutedASR(**common)

    def offline_primary(self, wav_path: str) -> DecodeOutput:
        from realtime_transcribe import read_wave

        samples, sample_rate = read_wave(wav_path)
        before = _rss_bytes()
        recognizer = self.single_asr._get("rz")
        started = time.perf_counter()
        text = self.single_asr._decode(recognizer, samples, sample_rate)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return DecodeOutput(text, len(samples) / sample_rate, elapsed_ms, [elapsed_ms],
                            max(before, _rss_bytes()))

    def stream(self, wav_path: str, *, refine: bool, single_ja: bool) -> DecodeOutput:
        from realtime_transcribe import (AudioHistory, PartialPrinter, Refiner, SessionStats,
                                         build_vad, drain_segments, read_wave, run_stream,
                                         wav_chunks)

        samples, sample_rate = read_wave(wav_path)
        asr = self.single_asr if single_ja else self.balanced_asr
        asr.reset_session()
        vad = build_vad(self.min_silence, self.max_speech)
        stats = SessionStats()
        capture = _CaptureServer()
        printer = PartialPrinter(enabled=False, server=capture)
        history = AudioHistory(sample_rate)
        refiner = Refiner(asr, history, sample_rate, printer, stats=stats) if refine else None
        before = _rss_bytes()
        started = time.perf_counter()
        run_stream(wav_chunks(samples, sample_rate, realtime=False), vad, sample_rate, asr,
                   stats, printer, refiner, history)
        vad.flush()
        drain_segments(vad, sample_rate, asr, stats, printer, history, refiner=refiner)
        if refiner is not None:
            refiner.maybe_refine(0, force=True)
            refiner._task_queue.join()
        elapsed_ms = (time.perf_counter() - started) * 1000
        events = capture.refines if refine and capture.refines else capture.finals
        text = "\n".join(event["text"] for event in events if event.get("text", "").strip())
        return DecodeOutput(text, len(samples) / sample_rate, elapsed_ms,
                            list(stats.latencies_ms), max(before, _rss_bytes()), stats.segments)

    def decode(self, mode: str, wav_path: str) -> DecodeOutput:
        if mode == "offline_primary":
            return self.offline_primary(wav_path)
        return self.stream(wav_path, refine=mode == "stream_refine",
                           single_ja=mode == "stream_single_ja")


def score_hypotheses(entries: list[dict[str, Any]], hypotheses: list[dict[str, Any]],
                     modes: Iterable[str]) -> dict[str, Any]:
    by_id = {entry["id"]: entry for entry in entries}
    term_vocabulary = {str(term) for entry in entries for term in entry.get("terms", [])}
    rows_by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for hypothesis in hypotheses:
        entry = by_id[hypothesis["id"]]
        counts = edit_counts(entry["text"], hypothesis["text"])
        tp, fn, fp = term_counts(entry.get("terms", []), hypothesis["text"], term_vocabulary)
        expected_digits = (entry["digits"] if "digits" in entry
                           else extract_digit_runs(entry["text"]))
        has_digit_case = bool(expected_digits)
        row = dict(hypothesis)
        row.update({
            "category": entry["category"],
            "reference": entry["text"],
            "cer": counts.cer,
            "substitutions": counts.substitutions,
            "deletions": counts.deletions,
            "insertions": counts.insertions,
            "reference_chars": counts.reference_length,
            "leading_deletion": counts.leading_deletion,
            "trailing_deletion": counts.trailing_deletion,
            "term_tp": tp, "term_fn": fn, "term_fp": fp,
            "digits_evaluated": has_digit_case,
            "digits_exact": (digits_exact(entry["text"], hypothesis["text"], expected_digits)
                             if has_digit_case else None),
            "abnormal_repetition": abnormal_repetition(hypothesis["text"]),
        })
        rows_by_mode[hypothesis["mode"]].append(row)

    def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        ref_chars = sum(row["reference_chars"] for row in rows)
        substitutions = sum(row["substitutions"] for row in rows)
        deletions = sum(row["deletions"] for row in rows)
        insertions = sum(row["insertions"] for row in rows)
        tp, fn, fp = (sum(row[key] for row in rows) for key in ("term_tp", "term_fn", "term_fp"))
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (2 * precision * recall / (precision + recall)
              if precision is not None and recall is not None and precision + recall else None)
        digit_rows = [row for row in rows if row["digits_evaluated"]]
        latencies = [value for row in rows for value in row.get("final_latencies_ms", [])]
        audio_s = sum(row["audio_s"] for row in rows)
        decode_s = sum(row["decode_ms"] for row in rows) / 1000
        return {
            "samples": len(rows),
            "cer": (substitutions + deletions + insertions) / ref_chars if ref_chars else 0.0,
            "substitutions": substitutions, "deletions": deletions, "insertions": insertions,
            "reference_chars": ref_chars,
            "leading_deletion_count": sum(bool(row["leading_deletion"]) for row in rows),
            "trailing_deletion_count": sum(bool(row["trailing_deletion"]) for row in rows),
            "term_precision": precision, "term_recall": recall, "term_f1": f1,
            "digits_exact_rate": (sum(bool(row["digits_exact"]) for row in digit_rows) / len(digit_rows)
                                  if digit_rows else None),
            "rtf": decode_s / audio_s if audio_s else 0.0,
            "decode_latency_ms_p50": percentile([row["decode_ms"] for row in rows], 0.50),
            "decode_latency_ms_p95": percentile([row["decode_ms"] for row in rows], 0.95),
            "final_latency_ms_p50": percentile(latencies, 0.50),
            "final_latency_ms_p95": percentile(latencies, 0.95),
            "max_rss_bytes": max((row.get("max_rss_bytes", 0) for row in rows), default=0),
            "empty_rate": sum(not row["text"].strip() for row in rows) / len(rows) if rows else 0.0,
            "abnormal_repetition_rate": (sum(bool(row["abnormal_repetition"]) for row in rows)
                                         / len(rows) if rows else 0.0),
        }

    result: dict[str, Any] = {"modes": {}}
    for mode in modes:
        rows = rows_by_mode.get(mode, [])
        categories = sorted({row["category"] for row in rows})
        result["modes"][mode] = {
            "overall": aggregate(rows),
            "categories": {category: aggregate([row for row in rows if row["category"] == category])
                           for category in categories},
        }
    return result


def render_markdown(metrics: dict[str, Any], hypotheses: list[dict[str, Any]]) -> str:
    lines = ["# Japanese Streaming ASR Evaluation", "", "## Overall", "",
             "| mode | samples | CER | S / D / I | term P / R / F1 | digits exact | RTF | p50 / p95 final ms | empty | repeat | max RSS MiB |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]

    def pct(value):
        return "n/a" if value is None else f"{100 * value:.2f}%"

    def num(value):
        return "n/a" if value is None else f"{value:.1f}"

    for mode, data in metrics["modes"].items():
        item = data["overall"]
        lines.append(
            f"| {mode} | {item['samples']} | {pct(item['cer'])} | "
            f"{item['substitutions']} / {item['deletions']} / {item['insertions']} | "
            f"{pct(item['term_precision'])} / {pct(item['term_recall'])} / {pct(item['term_f1'])} | "
            f"{pct(item['digits_exact_rate'])} | {item['rtf']:.4f} | "
            f"{num(item['final_latency_ms_p50'])} / {num(item['final_latency_ms_p95'])} | "
            f"{pct(item['empty_rate'])} | {pct(item['abnormal_repetition_rate'])} | "
            f"{item['max_rss_bytes'] / 1024 / 1024:.1f} |")
    lines += ["", "## Category breakdown", "",
              "| mode | category | samples | CER | leading / trailing missing | term F1 | digits exact | empty |",
              "|---|---|---:|---:|---:|---:|---:|---:|"]
    for mode, data in metrics["modes"].items():
        for category, item in data["categories"].items():
            lines.append(
                f"| {mode} | {category} | {item['samples']} | {pct(item['cer'])} | "
                f"{item['leading_deletion_count']} / {item['trailing_deletion_count']} | "
                f"{pct(item['term_f1'])} | {pct(item['digits_exact_rate'])} | "
                f"{pct(item['empty_rate'])} |")
    lines += ["", "Boundary missing counts are conservative alignment-based counts: only leading or trailing reference deletions are counted.",
              "", "## Hypotheses", "", "| id | mode | category | reference | hypothesis | CER |", "|---|---|---|---|---|---:|"]
    for row in hypotheses:
        def esc(value):
            return str(value).replace("|", "\\|").replace("\n", "<br>")
        lines.append(f"| {esc(row['id'])} | {esc(row['mode'])} | {esc(row['category'])} | "
                     f"{esc(row['reference'])} | {esc(row['text'])} | {pct(row['cer'])} |")
    return "\n".join(lines) + "\n"


def write_reports(output_dir: str | os.PathLike[str], metrics: dict[str, Any],
                  hypotheses: list[dict[str, Any]]) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (destination / "hypotheses.jsonl").open("w", encoding="utf-8") as stream:
        for row in hypotheses:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    (destination / "report.md").write_text(render_markdown(metrics, hypotheses), encoding="utf-8")


def default_output_dir() -> Path:
    return ROOT / "artifacts" / "ja_eval" / datetime.now().strftime("%Y%m%d-%H%M%S")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="JSONL evaluation manifest")
    parser.add_argument("--output", help="report directory (default: timestamped artifacts/ja_eval)")
    parser.add_argument("--modes", nargs="+", choices=DEFAULT_MODES, default=list(DEFAULT_MODES))
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--min-silence", type=float, default=0.35)
    parser.add_argument("--max-speech", type=float, default=12.0)
    args = parser.parse_args(argv)
    try:
        entries = load_manifest(args.manifest)
    except ManifestError as exc:
        parser.error(str(exc))
    available, missing = model_status()
    if not available:
        print("integration evaluation skipped; missing: " + ", ".join(missing), file=sys.stderr)
        return 0
    evaluator = Evaluator(args.threads, args.min_silence, args.max_speech)
    hypotheses: list[dict[str, Any]] = []
    for entry in entries:
        if not Path(entry["wav_path"]).is_file():
            parser.error(f"audio file not found for {entry['id']}: {entry['wav']}")
        for mode in args.modes:
            decoded = evaluator.decode(mode, entry["wav_path"])
            hypotheses.append({
                "id": entry["id"], "mode": mode, "text": decoded.text,
                "audio_s": decoded.audio_s, "decode_ms": decoded.decode_ms,
                "final_latencies_ms": decoded.final_latencies_ms,
                "max_rss_bytes": decoded.max_rss_bytes, "segments": decoded.segments,
            })
            print(f"[{entry['id']}/{mode}] {decoded.text}")
    metrics = score_hypotheses(entries, hypotheses, args.modes)
    metrics["environment"] = environment_metadata()
    metrics["settings"] = {"threads": args.threads, "min_silence": args.min_silence,
                           "max_speech": args.max_speech, "modes": args.modes,
                           "manifest_sha256": _file_sha256(Path(args.manifest))}
    scored = []
    by_id = {entry["id"]: entry for entry in entries}
    for row in hypotheses:
        entry = by_id[row["id"]]
        counts = edit_counts(entry["text"], row["text"])
        scored.append({**row, "category": entry["category"], "reference": entry["text"],
                       "cer": counts.cer})
    output = Path(args.output) if args.output else default_output_dir()
    write_reports(output, metrics, scored)
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
