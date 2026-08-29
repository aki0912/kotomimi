# Kotomimi Japanese ASR Evaluation

- Execution: **PASS**
- Release gate: **NOT ELIGIBLE**
- Suite: `quality-stress` v1
- Purpose: `quality_stress`
- Quality status: `experimental`
- System: `hayamimi-ja`
- Git commit: `6261f9cbe6cf047ff0e9e37d7c8aafc4c1769cdd`
- Git worktree dirty: `false`
- Punctuation: `off`
- QC view: `stress`

## Overall

| normalized CER | raw CER | S / D / I | exact | RTF | p50 / p95 ms | peak RSS MiB | failures |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 19.11% | 24.27% | 5896 / 9801 / 1382 | 38.20% | 0.0103 | 52.4 / 130.0 | 793.1 | 0 |

Dataset macro CER: **15.48%**

## Datasets

| dataset | samples | normalized CER | raw CER | S / D / I |
|---|---:|---:|---:|---:|
| common_voice_ja_26 | 3381 | 22.67% | 27.62% | 4852 / 9243 / 1149 |
| fleurs_ja | 446 | 8.30% | 14.12% | 1044 / 558 / 233 |

## Dataset provenance

| dataset | version / revision | split | view | license / policy | selected | audit |
|---|---|---|---|---|---:|---|
| common_voice_ja_26 | `26.0` | test | stress | CC0-1.0 / strict | 3381 | not-run |
| fleurs_ja | `70bb2e84b976b7e960aa89f1c648e09c59f894dd` | test | stress | CC-BY-4.0 / strict | 446 | not-run |

## Attribution

- Common Voice Scripted Speech 26.0 - Japanese — Mozilla Foundation / Common Voice contributors; CC0-1.0; https://mozilladatacollective.com/datasets/cmqim4lxy00tunr07cjkcupeg
- FLEURS - Japanese — Google; CC-BY-4.0; https://huggingface.co/datasets/google/fleurs

## Reproducibility

- Suite lock SHA-256: `8c981744a9623bcc6cecb23ff4305ee20ec60966f56fe10f12f8c4db4afad848`
- Suite manifest SHA-256: `8d3ba49f7898c76cb8a3d85a9b1d071bef7391d4c6e4823e54095a1bfcfe7d9d`
- Threads: 4
- Platform: macOS-26.6.2-arm64-arm-64bit

Stress contains QC-excluded clips and must not be presented as representative accuracy.
Peak RSS is process-wide and includes the loaded ASR model.
