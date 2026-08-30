# Kotomimi Japanese ASR Evaluation

- Execution: **PASS**
- Release gate: **ELIGIBLE**
- Suite: `fleurs-clean-approved` v1
- Purpose: `clean_regression`
- Quality status: `approved`
- System: `hayamimi-ja`
- Git commit: `20aabaeefe4af4c56d618f2ed4a40c45b35ac39b`
- Git worktree dirty: `false`
- Punctuation: `off`
- QC view: `clean`

## Overall

| normalized CER | raw CER | S / D / I | exact | RTF | p50 / p95 ms | peak RSS MiB | failures |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 9.43% | 15.05% | 570 / 318 / 107 | 23.53% | 0.0091 | 119.7 / 191.0 | 598.2 | 0 |

Dataset macro CER: **9.43%**

## Datasets

| dataset | samples | normalized CER | raw CER | S / D / I |
|---|---:|---:|---:|---:|
| fleurs_ja | 204 | 9.43% | 15.05% | 570 / 318 / 107 |

## Dataset provenance

| dataset | version / revision | split | view | license / policy | selected | audit |
|---|---|---|---|---|---:|---|
| fleurs_ja | `70bb2e84b976b7e960aa89f1c648e09c59f894dd` | test | clean | CC-BY-4.0 / strict | 204 | approved |

## Attribution

- FLEURS - Japanese — Google; CC-BY-4.0; https://huggingface.co/datasets/google/fleurs

## Reproducibility

- Suite lock SHA-256: `3e277137315f2eaaa81fedfb3e24ad583c02348f62df735a10eb8a7440953389`
- Suite manifest SHA-256: `78c11c1d44ff15471cb6359c54ca1344aab239802270a36e06e9799cbe3513ce`
- Threads: 4
- Platform: macOS-26.6.2-arm64-arm-64bit

Clean is selected only by pre-ASR QC rules and remains a candidate until re-audited.
Peak RSS is process-wide and includes the loaded ASR model.
