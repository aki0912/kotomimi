# QC report: fleurs_ja

- Dataset version: `70bb2e84b976b7e960aa89f1c648e09c59f894dd`
- Source split: `test`
- Input rows: 650
- Official rows: 650
- Clean rows: 204
- Stress rows: 446
- Hard failures: 0
- Speech activity method: `20ms-frame-rms>=configured-dbfs`
- Speech frame: 20 ms
- Speech threshold: -40.0 dBFS

The official view retains every evaluable source row. The clean view is a
secondary subset only; it must not replace the official benchmark result.
No ASR hypothesis is used for exclusion.

## Flag counts

| flag | count | clean exclusion |
|---|---:|:---:|
| `high_speech_fraction` | 270 | yes |
| `latin_mixed` | 66 | no |
| `long_leading_silence` | 174 | yes |
| `long_trailing_silence` | 79 | yes |
| `low_speech_fraction` | 79 | yes |
| `possible_clipping` | 2 | yes |
| `very_quiet` | 79 | yes |

## Duplicate groups

| kind | groups | affected rows |
|---|---:|---:|
| `source_id` | 0 | 0 |
| `source_audio` | 0 | 0 |
| `prepared_pcm` | 0 | 0 |
| `raw_text` | 223 | 552 |
| `audio_and_text` | 0 | 0 |
| `speaker_and_text` | 0 | 0 |
