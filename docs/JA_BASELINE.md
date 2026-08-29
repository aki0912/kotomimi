# Japanese ASR Baseline (PR 0)

This document freezes the evaluation procedure before any Japanese recognition,
VAD, model-selection, or CLI-default changes.

## Evaluation design

`scripts/eval_ja_streaming.py` reads one JSONL manifest and evaluates every
entry through the same four named paths:

- `offline_primary`: the complete clip is decoded directly by the existing
  ReazonSpeech recognizer.
- `stream_fast`: the existing balanced pipeline, production Silero VAD, and
  fast final output, without the Refiner result.
- `stream_refine`: the same balanced VAD pipeline, scored from Refiner output
  when available (otherwise its fast final fallback).
- `stream_single_ja`: the VAD fast path equivalent to
  `--mode single --lang ja`.

Relative WAV paths are resolved from the manifest directory. Required JSONL
fields are `id`, `wav`, `text`, and `category`; optional fields are `terms`,
`digits`, `speaker_group`, `license_source`, and `notes`.

Example:

```json
{"id":"ja_clean_001","wav":"ja_clean_001.wav","text":"今日は東京都多摩市で会議をします。","category":"clean_mic","terms":["東京都多摩市"],"digits":[]}
```

Run:

```bash
python scripts/eval_ja_streaming.py \
  --manifest testdata/eval_ja/manifest.jsonl \
  --output artifacts/ja_eval/current
```

The output directory contains `metrics.json`, `hypotheses.jsonl`, and
`report.md`. Metrics use NFKC normalization with punctuation and whitespace
removed. CER is micro-averaged. Leading/trailing missing counts only count an
optimal alignment that begins/ends with a reference deletion. Term precision
uses the manifest-wide term vocabulary, and digit exactness compares the
ordered digit strings declared by `digits`.

## Baseline status

- Baseline revision described by the development plan:
  `acc46cc2d6a10e4d29caa00469f30e5ad2caf307`.
- Environment used for PR 0 setup: macOS, Apple Silicon (`arm64`), Python
  3.11.9, sherpa-onnx 1.13.6.
- Before changes: `python -m pytest tests -q` completed with 83 passed and
  4 skipped in 1.57 seconds.
- Japanese integration evaluation: not run. The checkout had neither
  `models/` nor `testdata/`; therefore no CER, latency, RTF, or RSS baseline is
  claimed in this PR.

When an integration run is available, `metrics.json` records the OS, machine,
Python and sherpa-onnx versions, model directory names, and the Silero VAD
SHA-256 alongside the settings. Keep the generated reports under `artifacts/`;
models and evaluation audio remain outside Git.
