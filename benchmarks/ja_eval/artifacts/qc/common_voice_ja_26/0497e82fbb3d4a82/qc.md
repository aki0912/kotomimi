# QC report: common_voice_ja_26

- Dataset version: `26.0`
- Source split: `test`
- Input rows: 9020
- Official rows: 9020
- Clean rows: 5639
- Stress rows: 3381
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
| `high_speech_fraction` | 2 | yes |
| `latin_mixed` | 59 | no |
| `long_leading_silence` | 1621 | yes |
| `long_trailing_silence` | 2604 | yes |
| `low_japanese_ratio` | 3 | yes |
| `low_speech_fraction` | 492 | yes |
| `possible_clipping` | 1 | yes |
| `repeated_chars` | 15 | yes |
| `too_short` | 1 | yes |
| `very_long_text` | 3 | no |
| `very_quiet` | 222 | yes |
| `very_short_text` | 28 | no |

## Duplicate groups

| kind | groups | affected rows |
|---|---:|---:|
| `source_id` | 0 | 0 |
| `source_audio` | 0 | 0 |
| `prepared_pcm` | 0 | 0 |
| `raw_text` | 0 | 0 |
| `audio_and_text` | 0 | 0 |
| `speaker_and_text` | 0 | 0 |
