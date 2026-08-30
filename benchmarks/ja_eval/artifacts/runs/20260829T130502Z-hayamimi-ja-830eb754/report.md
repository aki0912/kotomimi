# Kotomimi Japanese ASR Evaluation

- Status: **PASS**
- Suite: `minimum-fleurs` v1
- System: `hayamimi-ja`
- Git commit: `830eb754dec7baab347806585525229eac64f41c`
- Git worktree dirty: `false`
- Punctuation: `off`
- QC view: `official`

## Overall

| normalized CER | raw CER | S / D / I | exact | RTF | p50 / p95 ms | peak RSS MiB | failures |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8.96% | 14.78% | 742 / 443 / 163 | 20.67% | 0.0091 | 114.2 / 178.6 | 743.0 | 0 |

Dataset macro CER: **8.96%**

## Datasets

| dataset | samples | normalized CER | raw CER | S / D / I |
|---|---:|---:|---:|---:|
| fleurs_ja | 300 | 8.96% | 14.78% | 742 / 443 / 163 |

## Dataset provenance

| dataset | version / revision | split | license / policy | selected | audit |
|---|---|---|---|---:|---|
| fleurs_ja | `70bb2e84b976b7e960aa89f1c648e09c59f894dd` | test | CC-BY-4.0 / strict | 300 | not-run |

## Attribution

- FLEURS - Japanese — Google; CC-BY-4.0; https://huggingface.co/datasets/google/fleurs

## Reproducibility

- Suite lock SHA-256: `0be8aa05f7138ffb769aa91d32b26d79a8d06ff35c5c9392a6c1417641f0e3ed`
- Suite manifest SHA-256: `098c528a90e8e4361d87bb716ab9f637df974d57ae5ca84c19e3aa36bf6dd029`
- Threads: 4
- Platform: macOS-26.6.2-arm64-arm-64bit

This report uses the official view. QC flags are reported but are not used to remove clips.
Peak RSS is process-wide and includes the loaded ASR model.
