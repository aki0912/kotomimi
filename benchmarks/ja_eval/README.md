# Kotomimi Japanese ASR Benchmark

This package is the commercial-use evaluation-data boundary for Kotomimi.
PR E0 intentionally implements only the registry, schemas, fail-closed license
gate, and model-free CLI. Dataset download, preparation, QC, and ASR execution
arrive in later PRs.

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

See `LICENSE_POLICY.md` and `THIRD_PARTY_DATASETS.md` before acquiring data.
