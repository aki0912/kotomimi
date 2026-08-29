# Kotomimi Japanese ASR Evaluation

- Execution: **PASS**
- Release gate: **NOT ELIGIBLE**
- Suite: `official-experimental` v1
- Purpose: `official_regression`
- Quality status: `experimental`
- System: `hayamimi-ja`
- Git commit: `6261f9cbe6cf047ff0e9e37d7c8aafc4c1769cdd`
- Git worktree dirty: `false`
- Punctuation: `off`
- QC view: `official`

## Overall

| normalized CER | raw CER | S / D / I | exact | RTF | p50 / p95 ms | peak RSS MiB | failures |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 17.77% | 22.99% | 2599 / 3182 / 581 | 33.23% | 0.0097 | 50.6 / 143.0 | 750.0 | 0 |

Dataset macro CER: **16.55%**

## Datasets

| dataset | samples | normalized CER | raw CER | S / D / I |
|---|---:|---:|---:|---:|
| common_voice_ja_26 | 1000 | 24.15% | 28.97% | 1857 / 2739 / 418 |
| fleurs_ja | 300 | 8.96% | 14.78% | 742 / 443 / 163 |

## Dataset provenance

| dataset | version / revision | split | view | license / policy | selected | audit |
|---|---|---|---|---|---:|---|
| common_voice_ja_26 | `26.0` | test | official | CC0-1.0 / strict | 1000 | experimental |
| fleurs_ja | `70bb2e84b976b7e960aa89f1c648e09c59f894dd` | test | official | CC-BY-4.0 / strict | 300 | experimental |

## Attribution

- Common Voice Scripted Speech 26.0 - Japanese — Mozilla Foundation / Common Voice contributors; CC0-1.0; https://mozilladatacollective.com/datasets/cmqim4lxy00tunr07cjkcupeg
- FLEURS - Japanese — Google; CC-BY-4.0; https://huggingface.co/datasets/google/fleurs

## Reproducibility

- Suite lock SHA-256: `ac44a99d429252f2aae377019cca69be2cde55cabe5790f90a8b5fe9081b636b`
- Suite manifest SHA-256: `4aae6edd8367c54c4af259e7bc526831d77c95b8bef3a53e296b4cfb3204849e`
- Threads: 4
- Platform: macOS-26.6.2-arm64-arm-64bit

Official retains every evaluable clip and is experimental, not a release gate.
Peak RSS is process-wide and includes the loaded ASR model.
