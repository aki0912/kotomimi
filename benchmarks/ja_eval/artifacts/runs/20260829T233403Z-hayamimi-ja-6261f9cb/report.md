# Kotomimi Japanese ASR Evaluation

- Execution: **PASS**
- Release gate: **NOT ELIGIBLE**
- Suite: `fleurs-clean-candidate` v1
- Purpose: `clean_candidate`
- Quality status: `candidate`
- System: `hayamimi-ja`
- Git commit: `6261f9cbe6cf047ff0e9e37d7c8aafc4c1769cdd`
- Git worktree dirty: `false`
- Punctuation: `off`
- QC view: `clean`

## Overall

| normalized CER | raw CER | S / D / I | exact | RTF | p50 / p95 ms | peak RSS MiB | failures |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 9.43% | 15.05% | 570 / 318 / 107 | 23.53% | 0.0092 | 121.2 / 190.1 | 599.0 | 0 |

Dataset macro CER: **9.43%**

## Datasets

| dataset | samples | normalized CER | raw CER | S / D / I |
|---|---:|---:|---:|---:|
| fleurs_ja | 204 | 9.43% | 15.05% | 570 / 318 / 107 |

## Dataset provenance

| dataset | version / revision | split | view | license / policy | selected | audit |
|---|---|---|---|---|---:|---|
| fleurs_ja | `70bb2e84b976b7e960aa89f1c648e09c59f894dd` | test | clean | CC-BY-4.0 / strict | 204 | pending |

## Attribution

- FLEURS - Japanese — Google; CC-BY-4.0; https://huggingface.co/datasets/google/fleurs

## Reproducibility

- Suite lock SHA-256: `924974da0256264ef01a8249895151fdb7b1f2d7bacd3626f414d18d4d57c7cf`
- Suite manifest SHA-256: `78c11c1d44ff15471cb6359c54ca1344aab239802270a36e06e9799cbe3513ce`
- Threads: 4
- Platform: macOS-26.6.2-arm64-arm-64bit

Clean is selected only by pre-ASR QC rules and remains a candidate until re-audited.
Peak RSS is process-wide and includes the loaded ASR model.
