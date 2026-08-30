# Kotomimi Japanese ASR Evaluation

- Status: **PASS**
- Suite: `minimum-strict` v1
- System: `hayamimi-ja`
- Git commit: `04f4aea874e3b6ed324c798f57324e447ff17644`
- Git worktree dirty: `false`
- Punctuation: `off`
- QC view: `official`

## Overall

| normalized CER | raw CER | S / D / I | exact | RTF | p50 / p95 ms | peak RSS MiB | failures |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 17.77% | 22.99% | 2599 / 3182 / 581 | 33.23% | 0.0092 | 48.4 / 137.0 | 748.8 | 0 |

Dataset macro CER: **16.55%**

## Datasets

| dataset | samples | normalized CER | raw CER | S / D / I |
|---|---:|---:|---:|---:|
| common_voice_ja_26 | 1000 | 24.15% | 28.97% | 1857 / 2739 / 418 |
| fleurs_ja | 300 | 8.96% | 14.78% | 742 / 443 / 163 |

## Dataset provenance

| dataset | version / revision | split | license / policy | selected | audit |
|---|---|---|---|---:|---|
| common_voice_ja_26 | `26.0` | test | CC0-1.0 / strict | 1000 | not-run |
| fleurs_ja | `70bb2e84b976b7e960aa89f1c648e09c59f894dd` | test | CC-BY-4.0 / strict | 300 | not-run |

## Attribution

- Common Voice Scripted Speech 26.0 - Japanese — Mozilla Foundation / Common Voice contributors; CC0-1.0; https://mozilladatacollective.com/datasets/cmqim4lxy00tunr07cjkcupeg
- FLEURS - Japanese — Google; CC-BY-4.0; https://huggingface.co/datasets/google/fleurs

## Reproducibility

- Suite lock SHA-256: `3fd1612874c2e9adb89b2fa4fc5f87fed47e6bdf2c436762429fa1e87d0cbc9e`
- Suite manifest SHA-256: `57890d1ed3e3dc761f4718293a431878e8f570b42a073d0a13285d89932b1204`
- Threads: 4
- Platform: macOS-26.6.2-arm64-arm-64bit

This report uses the official view. QC flags are reported but are not used to remove clips.
Peak RSS is process-wide and includes the loaded ASR model.
