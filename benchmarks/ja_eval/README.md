# Kotomimi Japanese ASR Benchmark

This package is the commercial-use evaluation-data boundary for Kotomimi.
PR E0 provides the registry, schemas, and fail-closed license gate. PR E1 adds
the pinned FLEURS Japanese adapter and offline evaluation. PR E2 adds the
Common Voice Japanese 26.0 archive adapter and the 1,300-clip `minimum-strict`
suite.

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

Prepare and evaluate FLEURS:

```bash
python -m kotomimi_eval dataset download fleurs_ja
python -m kotomimi_eval dataset prepare fleurs_ja
python -m kotomimi_eval dataset verify fleurs_ja
python -m kotomimi_eval suite build minimum-fleurs
python -m kotomimi_eval suite verify minimum-fleurs
python -m kotomimi_eval evaluate \
  --suite minimum-fleurs \
  --system hayamimi-ja \
  --threads 4 \
  --no-punctuate
```

The adapter always requests `google/fleurs`, configuration `ja_jp`, split
`test`, revision `70bb2e84b976b7e960aa89f1c648e09c59f894dd`, and exactly 650
rows. Prepared audio is 16 kHz mono PCM-16 FLAC without normalization or
silence trimming. `reference_raw`, NFC text, and evaluation-normalized text are
stored independently. QC flags do not remove clips from the official view.

Prepare Common Voice after accepting its terms in Mozilla Data Collective:

```bash
python -m kotomimi_eval dataset import common_voice_ja_26 \
  --archive path/to/common-voice-scripted-speech-26-0-japane-2e73a461.tar.gz
python -m kotomimi_eval dataset prepare common_voice_ja_26
python -m kotomimi_eval dataset verify common_voice_ja_26
python -m kotomimi_eval suite build minimum-strict
python -m kotomimi_eval suite verify minimum-strict
```

Authenticated API download is optional:

```bash
python -m pip install -e 'benchmarks/ja_eval[mdc]'
python -m kotomimi_eval dataset download common_voice_ja_26
```

Set the credential required by the official client before downloading.
Archives and extracted audio must remain local and must not
be re-hosted or reshared. The adapter accepts only the registered
`cv-corpus-26.0-2026-06-12/ja/test.tsv` and requires exactly 9,020 rows with
every referenced clip present. It never stores a raw `client_id`; a local,
uncommitted salt produces an opaque
speaker grouping ID instead.

`minimum-fleurs` selects 300 clips by stable hash with proportional gender and
duration strata. It never uses the first 300 rows. Reports record raw and
normalized CER, S/D/I, exact match, RTF, latency, RSS, model hashes, suite and
manifest hashes, license provenance, and audit status. A missing ASR model
causes only model-backed evaluation to exit clearly; registry, preparation,
suite, and metric tests remain model-free.

`minimum-strict` combines 1,000 Common Voice test clips with 300 FLEURS test
clips. Common Voice selection is deterministic and proportionally stratified
by duration, vote margin, sentence domain, age, and gender while spreading
selected clips across the provided speaker groups. This is an evaluation set;
neither source test split may be used for model or dictionary training.

Build model-independent QC views and human-audit samples:

```bash
python -m kotomimi_eval qc run --dataset common_voice_ja_26
python -m kotomimi_eval qc run --dataset fleurs_ja
python -m kotomimi_eval audit create \
  --dataset common_voice_ja_26 --count 200 --seed 20260829
python -m kotomimi_eval audit create \
  --dataset fleurs_ja --count 100 --seed 20260829
python -m kotomimi_eval audit serve --latest
```

QC never overwrites a prepared manifest. The official view keeps every
evaluable clip, while clean is a secondary subset based only on configured QC
flags. Reports state that speech activity is estimated with 20 ms frame RMS,
not model VAD. They must not be described as VAD measurements. Audit decisions
are appended and synced after every POST. The server rejects non-loopback bind
addresses; its default URL is `http://127.0.0.1:8765/`.

Use `python -m kotomimi_eval audit status --latest` to inspect completion and
the initial quality gate. Audit samples, decisions, and audio remain local.

See `LICENSE_POLICY.md` and `THIRD_PARTY_DATASETS.md` before acquiring data.
