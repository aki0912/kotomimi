# Kotomimi Japanese ASR Benchmark

This package is the commercial-use evaluation-data boundary for Kotomimi.
PR E0 provides the registry, schemas, and fail-closed license gate. PR E1 adds
the pinned FLEURS Japanese adapter, deterministic `minimum-fleurs` suite, basic
QC, and Hayamimi offline evaluation.

Install for development:

```bash
python -m pip install -e benchmarks/ja_eval
```

Inspect the registry and check licenses:

```bash
python -m kotomimi_eval dataset list
python -m kotomimi_eval license check --all
python -m kotomimi_eval license check cpjd --allow-sharealike
```

`license check --all` is expected to fail while manual-review datasets lack a
local approval. This is a safety property, not a setup error. Raw audio,
archives, complete manifests, audit decisions, and approval files stay local.

Prepare and evaluate FLEURS:

```bash
python -m kotomimi_eval dataset download fleurs_ja
python -m kotomimi_eval dataset prepare fleurs_ja
python -m kotomimi_eval dataset verify fleurs_ja
python -m kotomimi_eval suite build minimum-fleurs
python -m kotomimi_eval suite verify minimum-fleurs
python -m kotomimi_eval evaluate \
  --suite minimum-fleurs \
  --system hayamimi-ja \
  --threads 4 \
  --no-punctuate
```

The adapter always requests `google/fleurs`, configuration `ja_jp`, split
`test`, revision `70bb2e84b976b7e960aa89f1c648e09c59f894dd`, and exactly 650
rows. Prepared audio is 16 kHz mono PCM-16 FLAC without normalization or
silence trimming. `reference_raw`, NFC text, and evaluation-normalized text are
stored independently. QC flags do not remove clips from the official view.

`minimum-fleurs` selects 300 clips by stable hash with proportional gender and
duration strata. It never uses the first 300 rows. Reports record raw and
normalized CER, S/D/I, exact match, RTF, latency, RSS, model hashes, suite and
manifest hashes, license provenance, and audit status. A missing ASR model
causes only model-backed evaluation to exit clearly; registry, preparation,
suite, and metric tests remain model-free.

See `LICENSE_POLICY.md` and `THIRD_PARTY_DATASETS.md` before acquiring data.
