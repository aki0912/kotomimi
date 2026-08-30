# Audit report: fleurs_ja-clean-20260829-204-2ea731373775

- Dataset: `fleurs_ja`
- Version: `70bb2e84b976b7e960aa89f1c648e09c59f894dd`
- Source view: `clean`
- Status: **approved**
- Reviewed: 204 / 204
- Severe issue rate: 0.0% (maximum 5.0%)
- Truncated rate: 0.0% (maximum 2.0%)
- Approved for gate: `true`

This exact clean view is approved as a supplementary regression gate. It does not replace official results.

Duplicate labels are reported but do not automatically remove samples or fail
the gate; repeated text from different speakers can be valid evaluation data.

## Labels

| label | count |
|---|---:|
| `duplicate` | 31 |
| `minor_transcript_issue` | 1 |
| `ok` | 172 |

This aggregate report contains no sample IDs, references, audio paths, or speaker IDs.
