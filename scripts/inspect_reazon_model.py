#!/usr/bin/env python3
"""Inspect attributes returned by the installed ReazonSpeech recognizer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from asr_engine import ModelUnavailable, RoutedASR
from realtime_transcribe import read_wave


def _json_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return repr(value)


def inspect_result(wav_path: str, threads: int) -> dict[str, object]:
    samples, sample_rate = read_wave(wav_path)
    asr = RoutedASR(threads=threads, preload=False, forced_lang="ja")
    recognizer = asr._get("rz")
    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, samples)
    recognizer.decode_stream(stream)
    result = stream.result
    attributes = {}
    for name in sorted(item for item in dir(result) if not item.startswith("_")):
        value = getattr(result, name)
        if callable(value):
            continue
        attributes[name] = {
            "type": type(value).__name__,
            "value": _json_value(value),
        }
    return {
        "wav": str(Path(wav_path)),
        "result_type": type(result).__name__,
        "attributes": attributes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect-result", required=True, metavar="WAV")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        result = inspect_result(args.inspect_result, args.threads)
    except (ModelUnavailable, RuntimeError, OSError, AssertionError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
