# 商用利用可能・無償の日本語ASR評価データ基盤 開発計画

> Codex向け実装仕様書  
> 対象: `oboroge0/hayamimi` および日本語特化派生プロジェクト  
> 位置づけ: `japanese_asr_codex_development_plan.md` の **PR 0（評価基盤）を置き換える詳細計画**  
> 基準リビジョン: `acc46cc2d6a10e4d29caa00469f30e5ad2caf307`  
> 最終更新: 2026-08-29  
> 仮称: **Kotomimi Japanese ASR Benchmark**

---

## 0. この文書の目的

この文書は、次の条件を満たす日本語ASR評価データ基盤をCodexで実装するための計画である。

- 無料で取得できる。
- 商用製品・商用サービスの評価にも使用できるライセンスである。
- データの取得元、版、ライセンス、変換内容を追跡できる。
- 音声と正解テキストの最低限の品質を機械・人手の両方で確認できる。
- モデル単体評価と、VADを含むストリーミング評価を分けられる。
- 生データをGitHubへ再配布しなくても再現できる。
- 小規模な確認からリリース判定まで、同じ仕組みで段階的に評価できる。

この計画で構築するものは、学習用データセットではなく、**評価専用の再現可能なベンチマーク基盤**である。

---

# 1. 重要な前提

## 1.1 「オープン」と「商用利用可能」は同じではない

日本語音声コーパスには、無償公開されていても次の制限を持つものが多い。

- 研究目的のみ
- 非商用のみ
- 営利企業内でも非商用研究に限定
- 商用利用は別途問い合わせ・契約が必要
- 日本国著作権法30条の4の目的に限定
- 元動画・放送の権利が不明確
- 音声の再配布禁止

したがって、Codexは「ダウンロードできる」「Hugging Faceにある」「GitHubにある」という理由だけで採用してはならない。

## 1.2 本計画のライセンス判定方針

データセットは次の3段階に分ける。

| 区分 | 許可する条件 | 既定で利用 | 例 |
|---|---|---:|---|
| `strict` | CC0またはCC BY 4.0で、追加の商用禁止がない | はい | Common Voice、FLEURS、SPREDS-U1 |
| `sharealike` | CC BY-SA 4.0。商用利用は可能だが、派生物の配布条件に注意 | オプション | CPJD、JVNV、JNV |
| `manual-review` | 標準ライセンス以外の追加条件がある、または利用規約の確認が必要 | いいえ | ITA-Corpus-Rion |

次は常に拒否する。

- `NC`を含むCreative Commonsライセンス
- `research only`
- `non-commercial`
- 商用利用に個別許可が必要
- 著作権法30条の4の目的に限定
- ライセンス不明
- 配布元と原権利者の関係が説明できない

## 1.3 法務上の位置づけ

この文書はエンジニアリング上のライセンス・ゲート設計であり、法的助言ではない。
実際の製品リリース時には、保存したライセンス情報と利用規約を組織の法務担当者が確認できる状態にする。

---

# 2. 採用データセット

## 2.1 既定のコアセット

### A. Common Voice Scripted Speech 26.0 — Japanese

| 項目 | 内容 |
|---|---|
| 用途 | 多話者・多様な録音環境の読み上げ音声 |
| 採用split | `test.tsv` |
| ライセンス | CC0-1.0 |
| 版 | 26.0 / `cv-corpus-26.0-2026-06-12` |
| 期待件数 | 9,020クリップ |
| データセットID | `cmqim4lxy00tunr07cjkcupeg` |
| 取得 | Mozilla Data Collective APIまたは利用者が取得したtar.gz |
| 重要条件 | 話者の特定を試みない。データを再ホスト・再共有しない |

採用理由:

- 日本語版全体は多数話者を含み、年齢・性別・ドメイン等の自己申告メタデータがある。
- `test.tsv`は既に評価用splitとして提供されている。
- `up_votes`と`down_votes`を品質確認に利用できる。
- 実マイク・家庭環境・端末差を含みやすく、スタジオ音声だけでは見えない問題を検出できる。

制約:

- 読み上げ音声であり、自然会話ではない。
- 収録品質・発音にはばらつきがある。
- Common Voiceの公開ページは再ホスト・再共有を禁止しているため、生データや抽出音声をリポジトリへ含めない。

### B. Google FLEURS — Japanese `ja_jp`

| 項目 | 内容 |
|---|---|
| 用途 | 固定・再現可能な標準読み上げ評価 |
| 採用split | `ja_jp/test` |
| ライセンス | CC BY 4.0 |
| 固定revision | `70bb2e84b976b7e960aa89f1c648e09c59f894dd` |
| 期待件数 | 650クリップ |
| 取得 | Hugging Face `datasets` |

採用理由:

- 評価用データセットとして設計されている。
- 日本語を含む多言語で同じ設計を採用しており、他モデルとの比較がしやすい。
- 取得元revisionを固定しやすい。
- Common Voiceとは文章・話者・収録系統が異なり、同じ誤りに偏りにくい。

制約:

- 読み上げ音声であり、会話・雑音・長時間音声の代表ではない。
- CC BY 4.0の帰属表示を必ず生成する。

### C. NICT SPREDS-U1 — Japanese

| 項目 | 内容 |
|---|---|
| 用途 | 音声認識評価用に設計された統制条件の日本語発話 |
| ライセンス | CC BY 4.0 |
| 公開 | 無償一般公開・open access |
| 取得 | 利用者が取得したアーカイブをローカルimport |
| 実装上の扱い | `strict`だが、初期版では任意データセット |

採用理由:

- NICTが音声認識評価用として公開している。
- 複数言語でドメイン・人数・収録環境等をできる限り揃えている。
- Common Voiceより統制された音声を補完できる。

制約:

- 2026-08-29時点で公開ページがメンテナンス表示になる場合がある。
- 自動ダウンロードに依存するとCIや新規環境の構築が壊れやすい。
- 初期実装では`--archive PATH`による手動importを正式ルートにする。

## 2.2 商用利用可能な追加ストレスセット

### D. CPJD

| 項目 | 内容 |
|---|---|
| 正式名 | Crowdsourced Parallel Speech Corpus of Japanese Dialects |
| 用途 | 方言・アクセントのストレス評価 |
| 規模 | 21話者、各250文、20方言 |
| ライセンス | CC BY-SA 4.0 |
| プロファイル | `sharealike` |

評価用途:

- 方言別CER
- 標準語文と方言文の差
- 方言ごとの削除・置換傾向
- 1方言1話者に近い構成であることを考慮したストレステスト

注意:

- 日本の方言全体の平均性能を代表するものではない。
- 方言と話者が強く結びつくため、結果は「方言一般」ではなく「収録された話者・方言条件」に対する値として報告する。
- 生成物を配布する場合、CC BY-SA 4.0を継承する可能性があるため、生データ・変換音声・生成manifestは既定でGit管理外にする。

### E. JVNV

| 項目 | 内容 |
|---|---|
| 正式名 | Japanese emotional speech corpus with Verbal content and Nonverbal Vocalizations |
| 用途 | 感情発話、笑い・泣き等を含む音声の認識評価 |
| 規模 | 4話者、6感情、1,615発話、3.94時間 |
| ライセンス | CC BY-SA 4.0 |
| プロファイル | `sharealike` |

評価用途:

- 感情別CER
- 非言語音声の前後にある語頭・語尾欠落
- VADが笑い・泣きを発話区間としてどう扱うか
- 非言語区間を文字列として幻覚しないか

### F. JNV

| 項目 | 内容 |
|---|---|
| 正式名 | Japanese Nonverbal Vocalization corpus |
| 用途 | 非言語音声に対する誤文字起こし率 |
| 規模 | 4話者、420音声、約406.9秒 |
| ライセンス | CC BY-SA 4.0 |
| プロファイル | `sharealike` |

JNVには通常の文章正解を置かず、次を測る。

- `nonempty_output_rate`
- 1分あたりの幻覚文字数
- 最長幻覚文字列長
- false final数
- VADが音声として確定した割合

JNVは通常CERへ混ぜない。

## 2.3 手動レビュー後に利用できる候補

### G. ITA-Corpus-Rion

| 項目 | 内容 |
|---|---|
| 用途 | 50名の統制された高品質読み上げ音声 |
| 話者 | 男性25名・女性25名、年代分布あり |
| 音声 | 48kHz、24bit、mono、無響室 |
| 表示ライセンス | CC BY 4.0 |
| 追加条件 | データセットの転売禁止 |
| 取得 | 申請フォーム経由 |
| プロファイル | `manual-review` |

利点:

- スタジオ条件・多数話者で、入力品質を統制した評価に向く。
- ITA Corpus Emotionの100文はパブリックドメインのテキストである。

扱い:

- CC BY 4.0に加え「転売禁止」という追加条件が記載されている。
- ASR製品の社内評価には利用可能と解釈できる余地があるが、標準CC BYだけではないため既定セットに含めない。
- 利用する組織が条件を確認し、`licenses/approvals/ita_rion.json`を作成した場合だけ有効化する。
- 音声や変換音声の配布は行わない。

---

# 3. 明示的に採用しないデータセット

Codexは次の候補を自動的に追加してはならない。

| データセット | 不採用理由 |
|---|---|
| ReazonSpeechデータセット | 利用目的を日本国著作権法30条の4に限定する条件がある。一般的な商用評価データとして扱わない |
| JSUT | 音声の商用利用は別途問い合わせが必要 |
| JVS | 音声は研究・非商用が既定で、商用利用は別途確認が必要 |
| JSSS | 音声は研究・非商用に限定。一部テキストにも非商用条件がある |
| JECS | 音声は研究・非商用に限定 |
| J-CHAT | 商用利用不可と明記 |
| CSJ | 無料版があっても商用利用は個別相談。全データは有料 |
| CEJC | 全音声利用や商用条件が本計画の「無料・即利用可能」を満たさない |
| TEDxJP-10K | 元YouTube動画の個別権利・再構築条件を商用ベンチマークで一括保証しにくい |
| JTubeSpeech系 | YouTube由来かつ研究目的等の制限がある |
| MagicHub無償日本語コーパス | 多くがCC BY-NC-NDまたは非商用研究限定 |
| ライセンス不明のHugging Faceミラー | 元データの条件を上書きできない |

不採用リストは`benchmarks/ja_eval/config/denied_datasets.yaml`としてコード化し、誤採用をテストする。

---

# 4. 完成時のベンチマーク構成

## 4.1 `smoke`

目的:

- CLI・manifest・評価器が動くことだけを確認する。
- 精度判断には使用しない。

構成:

- ローカルに対象データがある場合のみ、各データセットから5〜10件。
- データがないCIでは、テスト中に生成する合成WAVと一時manifestを使用。
- 実データ音声をGitへ含めない。

## 4.2 `minimum-strict`

最小の品質確認に使う既定プロファイル。

| データセット | 目標件数 | 選択方法 |
|---|---:|---|
| Common Voice test | 1,000 | 話者・長さ・ドメイン・vote marginを考慮した決定的層化抽出 |
| FLEURS ja_jp test | 300 | 話者・長さで決定的層化抽出 |
| 合計 | 1,300 | 固定seed |

SPREDS-U1がローカルにある場合も、`minimum-strict`へ暗黙に混ぜない。
追加版は`minimum-strict-spreds`として別名にする。

## 4.3 `minimum-strict-spreds`

| データセット | 目標件数 |
|---|---:|
| Common Voice | 1,000 |
| FLEURS | 300 |
| SPREDS-U1 Japanese | 最大200、または全件が200未満なら全件 |

## 4.4 `minimum-extended`

`minimum-strict`に、商用利用可能なCC BY-SAストレスセットを加える。

| データセット | 目標件数 | 層化条件 |
|---|---:|---|
| CPJD | 200 | 20方言から均等 |
| JVNV | 120 | 6感情から均等、話者を分散 |
| JNV | 100 | 6感情・4話者を分散 |

## 4.5 `standard-strict`

- Common Voice 26.0 Japaneseの公式`test.tsv`全件
- FLEURS `ja_jp/test`全件
- SPREDS-U1 Japaneseが利用可能なら全件。ただし有無をレポートに明記

目的:

- リリース候補のモデル単体精度
- モデル変更前後の回帰比較
- データセット別マクロ平均

## 4.6 `standard-extended`

`standard-strict`に以下を全件追加する。

- CPJD
- JVNV
- JNV

## 4.7 `streaming-minimum`

分割済み音声をそのまま認識するのではなく、ローカルで連続音声へ合成して次を評価する。

- VAD境界
- 無音長の違い
- 連続発話
- 短い相づち
- 非言語音声の挿入
- 語頭・語尾欠落
- partialからfinalへの書き換え
- 確定遅延

生成音声は配布しない。再生成可能なrecipeだけをGit管理する。

---

# 5. リポジトリ構成

既存コードを大きく壊さず、評価基盤を独立したパッケージとして追加する。

```text
benchmarks/
  ja_eval/
    README.md
    LICENSE_POLICY.md
    THIRD_PARTY_DATASETS.md
    pyproject.toml
    requirements-eval.txt

    config/
      datasets.yaml
      suites.yaml
      denied_datasets.yaml
      normalization.yaml
      qc_thresholds.yaml

    schemas/
      manifest.schema.json
      audit.schema.json
      report.schema.json
      dataset_lock.schema.json

    src/
      kotomimi_eval/
        __init__.py
        __main__.py
        cli.py
        errors.py
        logging_utils.py

        config.py
        paths.py
        hashing.py
        subprocess_utils.py

        licensing/
          policy.py
          registry.py
          approvals.py
          attribution.py

        datasets/
          base.py
          common_voice.py
          fleurs.py
          spreds_u1.py
          cpjd.py
          jvnv.py
          jnv.py
          ita_rion.py

        prepare/
          archives.py
          audio.py
          text.py
          manifest.py
          dedupe.py
          sampling.py
          qc.py
          streaming.py

        audit/
          sampler.py
          server.py
          storage.py
          report.py

        evaluation/
          runner.py
          hayamimi_adapter.py
          metrics.py
          bootstrap.py
          aggregation.py
          regression.py

        reporting/
          json_report.py
          markdown_report.py
          html_report.py

    tests/
      fixtures/
        synthetic_dataset/
      test_license_policy.py
      test_archive_safety.py
      test_audio_qc.py
      test_text_normalization.py
      test_manifest.py
      test_sampling.py
      test_common_voice_adapter.py
      test_fleurs_adapter.py
      test_spreds_adapter.py
      test_cpjd_adapter.py
      test_jvnv_adapter.py
      test_jnv_metrics.py
      test_streaming_recipe.py
      test_metrics.py
      test_regression_gate.py

    recipes/
      streaming_minimum.yaml
      streaming_stress.yaml

    licenses/
      sources.yaml
      approvals/
        .gitkeep

    scripts/
      run_minimum.sh
      run_standard.sh
      run_audit.sh

    data/                 # 全てgitignore
      downloads/
      raw/
      prepared/
      manifests/
      streams/
      cache/

    artifacts/            # 原則gitignore。要約レポートだけ選択的に保存
      qc/
      audits/
      runs/
      comparisons/
```

ルートの`.gitignore`へ次を追加する。

```gitignore
benchmarks/ja_eval/data/
benchmarks/ja_eval/artifacts/audits/
benchmarks/ja_eval/artifacts/runs/*/hypotheses.jsonl
benchmarks/ja_eval/licenses/approvals/*.json
!benchmarks/ja_eval/licenses/approvals/.gitkeep
```

---

# 6. ライセンス・ゲート

## 6.1 `datasets.yaml`

例:

```yaml
schema_version: 1

datasets:
  common_voice_ja_26:
    display_name: Common Voice Scripted Speech 26.0 - Japanese
    adapter: common_voice
    version: "26.0"
    source_dataset_id: cmqim4lxy00tunr07cjkcupeg
    expected_archive_name: common-voice-scripted-speech-26-0-japane-2e73a461.tar.gz
    source_split: test
    license:
      spdx: CC0-1.0
      policy: strict
      commercial_use: true
      attribution_required: false
      redistribute_raw: false
      restrictions:
        - no_speaker_reidentification
        - no_rehosting
        - no_resharing
    source_url: https://mozilladatacollective.com/datasets/cmqim4lxy00tunr07cjkcupeg
    expected:
      rows: 9020

  fleurs_ja:
    display_name: Google FLEURS Japanese
    adapter: fleurs
    source_repo: google/fleurs
    source_revision: 70bb2e84b976b7e960aa89f1c648e09c59f894dd
    source_config: ja_jp
    source_split: test
    license:
      spdx: CC-BY-4.0
      policy: strict
      commercial_use: true
      attribution_required: true
      redistribute_raw: true
    expected:
      rows: 650

  spreds_u1_ja:
    display_name: NICT SPREDS-U1 Japanese
    adapter: spreds_u1
    version: "2025-07-08"
    source_split: official
    license:
      spdx: CC-BY-4.0
      policy: strict
      commercial_use: true
      attribution_required: true
    acquisition:
      mode: local_archive

  cpjd:
    display_name: CPJD
    adapter: cpjd
    license:
      spdx: CC-BY-SA-4.0
      policy: sharealike
      commercial_use: true
      attribution_required: true
      share_alike: true

  jvnv:
    display_name: JVNV
    adapter: jvnv
    license:
      spdx: CC-BY-SA-4.0
      policy: sharealike
      commercial_use: true
      attribution_required: true
      share_alike: true

  jnv:
    display_name: JNV
    adapter: jnv
    license:
      spdx: CC-BY-SA-4.0
      policy: sharealike
      commercial_use: true
      attribution_required: true
      share_alike: true

  ita_rion:
    display_name: ITA-Corpus-Rion
    adapter: ita_rion
    license:
      spdx: CC-BY-4.0
      policy: manual-review
      commercial_use: true
      attribution_required: true
      additional_terms:
        - no_resale
    acquisition:
      mode: local_archive
      approval_required: true
```

## 6.2 fail-closed

次の場合は処理を即時停止する。

- データセットがregistryにない。
- `commercial_use`が`true`ではない。
- SPDXが許可リストにない。
- `policy=manual-review`なのにapprovalファイルがない。
- 利用規約のsource URLがない。
- 取得した版とregistryのversion/revisionが一致しない。
- 期待件数が大きく変わった。

警告だけで続行してはならない。

## 6.3 approvalファイル

`manual-review`用のローカルファイル例:

```json
{
  "schema_version": 1,
  "dataset_id": "ita_rion",
  "approved_by": "organization-or-reviewer",
  "approved_at": "2026-08-29",
  "purpose": "internal commercial ASR evaluation",
  "terms_reviewed": [
    "CC-BY-4.0",
    "no resale"
  ],
  "allow_redistribution": false,
  "notes": "Audio and derived audio remain local."
}
```

approvalファイルには個人名・メールアドレス等を必須にしない。Gitへコミットしない。

## 6.4 `dataset.lock.json`

準備済みデータごとに次を保存する。

```json
{
  "schema_version": 1,
  "dataset_id": "fleurs_ja",
  "version": "main",
  "source_revision": "70bb2e84b976b7e960aa89f1c648e09c59f894dd",
  "source_split": "test",
  "source_config": "ja_jp",
  "license_spdx": "CC-BY-4.0",
  "prepared_at": "2026-08-29T00:00:00Z",
  "adapter_version": 1,
  "normalization_version": 1,
  "row_count": 650,
  "source_manifest_sha256": "...",
  "prepared_manifest_sha256": "...",
  "tool_versions": {
    "python": "3.11.x",
    "ffmpeg": "...",
    "datasets": "..."
  }
}
```

`prepared_at`は再現性判定に使わず、hash計算から除外する。

---

# 7. 取得フロー

## 7.1 共通ルール

- ダウンロード先は`data/downloads`。
- 展開先は`data/raw/<dataset_id>/<version>`。
- 変換先は`data/prepared/<dataset_id>/<version>`。
- `.part`ファイルを使い、完了後にatomic renameする。
- 既存ファイルを無条件に上書きしない。
- SHA-256を計算する。
- zip/tar展開時にpath traversalを拒否する。
- symlink/hardlinkを既定で拒否する。
- 予想外に巨大な展開を防ぐため、展開総サイズ上限を設定する。
- エラー時にAPIキー・URL署名・フォーム情報をログへ出さない。

## 7.2 Common Voice

CLI:

```bash
python -m kotomimi_eval dataset download common_voice_ja_26
```

前提:

- 利用者がMozilla Data Collectiveで利用規約を承諾する。
- API credentialを作成する。
- `MDC_API_KEY`等、公式ライブラリが要求する環境変数を設定する。

別経路:

```bash
python -m kotomimi_eval dataset import common_voice_ja_26 \
  --archive /path/to/common-voice-scripted-speech-26-0-japane-2e73a461.tar.gz
```

実装要件:

- `datacollective`ライブラリ経由の取得をサポートする。
- ライブラリ仕様変更に備え、ローカルarchive importを常に残す。
- `test.tsv`以外を評価manifestへ入れない。
- `clips/<path>`が全件存在するか検証する。
- `client_id`を外部出力レポートへそのまま載せず、dataset-local saltでhash化する。
- `up_votes`、`down_votes`、`sentence_domain`、年齢・性別等は、提供された値だけを使う。
- 話者の推定・再特定処理は一切実装しない。

## 7.3 FLEURS

CLI:

```bash
python -m kotomimi_eval dataset download fleurs_ja
```

実装例:

```python
from datasets import load_dataset

rows = load_dataset(
    "google/fleurs",
    "ja_jp",
    split="test",
    revision="70bb2e84b976b7e960aa89f1c648e09c59f894dd",
)
```

要件:

- revisionを省略しない。
- streamingモードではなく、評価に必要なデータをローカル固定する。
- 元のsample IDを保持する。
- 正解には`transcription`を使用し、`raw_transcription`等がある場合は両方保持する。
- 音声配列を直接永続化するときもsource hashを作る。
- 650件という期待件数を検証する。差があれば停止する。

## 7.4 SPREDS-U1

CLI:

```bash
python -m kotomimi_eval dataset import spreds_u1_ja \
  --archive /path/to/SPREDS-U1.zip
```

要件:

- ルートのREADME・利用条件を検出し、hashをlockへ保存する。
- 日本語ディレクトリは、既知の`jpn`等の候補を探索するが、複数候補が見つかった場合は自動決定しない。
- 音声と書き起こしの対応規則をadapter内に閉じ込める。
- 配布版のフォーマット変更に備え、fixture archiveによるテストを作る。
- 公開サイトの可用性に依存したCIを作らない。

## 7.5 CPJD / JVNV / JNV

初期版はローカルarchive importのみを実装する。

```bash
python -m kotomimi_eval dataset import cpjd --archive /path/to/cpjd.zip
python -m kotomimi_eval dataset import jvnv --archive /path/to/jvnv.zip
python -m kotomimi_eval dataset import jnv --archive /path/to/jnv.zip
```

理由:

- Google Driveや研究室サーバーのURLは変更される可能性がある。
- 利用者がライセンスページを確認して取得する流れを維持する。
- Codexがスクレイピング・ブラウザ自動操作を実装する必要はない。

## 7.6 ITA-Corpus-Rion

フォーム申請を自動化してはならない。

```bash
python -m kotomimi_eval dataset import ita_rion \
  --archive /path/to/downloaded_archive.zip \
  --approval benchmarks/ja_eval/licenses/approvals/ita_rion.json
```

---

# 8. 統一manifest

1行1JSONのJSONLを使用する。

```json
{
  "schema_version": 1,
  "sample_id": "common_voice_ja_26:test:8cf...",
  "dataset_id": "common_voice_ja_26",
  "dataset_version": "26.0",
  "source_split": "test",
  "source_sample_id": "...",
  "audio_path": "data/prepared/common_voice_ja_26/26.0/audio/8c/....flac",
  "source_audio_path": "clips/....mp3",
  "audio_sha256": "...",
  "pcm_sha256": "...",
  "sample_rate": 16000,
  "channels": 1,
  "duration_s": 4.21,
  "reference_raw": "iPhoneはとても高い",
  "reference_nfc": "iPhoneはとても高い",
  "reference_eval": "iphoneはとても高い",
  "speaker_id": "spk_8f...",
  "categories": ["read", "crowd", "technology_robotics"],
  "metadata": {
    "age": "twenties",
    "gender": "female_feminine",
    "up_votes": 3,
    "down_votes": 0
  },
  "license": {
    "spdx": "CC0-1.0",
    "policy": "strict",
    "attribution_key": "common_voice_ja_26"
  },
  "qc": {
    "hard_pass": true,
    "flags": ["long_leading_silence"],
    "rms_dbfs": -24.3,
    "peak": 0.73,
    "clipped_fraction": 0.0,
    "speech_fraction": 0.68
  }
}
```

## 8.1 ID規則

`sample_id`は次から生成する。

```text
sha256(dataset_id + "\0" + dataset_version + "\0" + source_split + "\0" + source_sample_id)
```

元のファイルパスだけに依存しない。

## 8.2 speaker ID

- 元データが話者IDを提供する場合のみ使用する。
- Common Voiceの`client_id`はそのまま外部レポートへ出さない。
- `speaker_id = sha256(dataset_id + local_secret_salt + source_speaker_id)`とする。
- saltはローカル生成し、Gitへ含めない。
- 評価の再現に話者hashそのものは不要であり、同一話者グルーピングだけに使う。

## 8.3 rawとnormalizedを分離

必ず次を保持する。

- `reference_raw`: 元データの表記
- `reference_nfc`: Unicode NFCのみ
- `reference_eval`: CER計算用の規定正規化

`reference_raw`を上書きしない。

---

# 9. 音声変換

## 9.1 標準形式

評価用のprepared audioは次に統一する。

- FLAC
- 16kHz
- mono
- PCM 16-bit相当
- 音量正規化なし
- 無音trimなし

音量正規化や無音trimをすると実環境性能を過大評価するため、既定では行わない。

## 9.2 ffmpeg

変換は既存プロジェクトが前提としているffmpegを使用する。

```bash
ffmpeg -nostdin -hide_banner -loglevel error \
  -i INPUT \
  -ac 1 -ar 16000 -sample_fmt s16 \
  OUTPUT.flac
```

要件:

- shell文字列を組み立てず、argument listで`subprocess.run`する。
- timeoutを設定する。
- stderrの全文を通常ログへ出さない。
- 変換後にffprobeまたはsoundfileで実フォーマットを検証する。
- source audioとprepared audioの両方にSHA-256を持つ。

---

# 10. 品質チェック

品質チェックは「データを消す処理」ではなく、まず**問題を可視化する処理**として設計する。

## 10.1 2種類のview

### `official`

- 公式splitを原則そのまま使用する。
- 除外するのは、欠損・破損・正解空・読めない形式等、評価不能な項目だけ。
- QCフラグがあっても残す。

### `clean`

- 事前定義された品質基準を満たすsubset。
- 主結果ではなく補助結果として出す。
- モデル出力を使って自動除外しない。

常に`official`と`clean`の両方を報告し、`clean`だけを総合値として宣伝しない。

## 10.2 hard failure

次は除外する。

- 音声ファイルがない。
- デコード不能。
- durationが0.1秒未満または60秒超。データセット仕様が別なら明示的にoverrideする。
- NaN/Infを含む。
- channel数が0。
- 正解テキストが空。
- NUL、未処理の制御文字を含む。
- manifest IDが重複。
- 同じsource sampleが複数splitへ混入。

hard failure件数が1件でもあれば、準備コマンドは非0終了にする。ただし`--allow-known-failures FILE`で明示的に承認した既知問題だけ除外できる。

## 10.3 音声QCフラグ

次は自動除外せずflagにする。

| フラグ | 既定目安 |
|---|---|
| `too_short` | 0.5秒未満 |
| `too_long` | 30秒超 |
| `very_quiet` | RMS -50 dBFS未満 |
| `very_loud` | RMS -3 dBFS超 |
| `possible_clipping` | `abs(sample) >= 0.999`が0.1%以上 |
| `dc_offset` | 絶対平均0.02超 |
| `long_leading_silence` | 先頭無音1.0秒超 |
| `long_trailing_silence` | 末尾無音1.0秒超 |
| `low_speech_fraction` | VAD speech fraction 0.15未満 |
| `high_speech_fraction` | VAD speech fraction 0.98超 |
| `duplicate_pcm` | PCM hashが別IDと一致 |

閾値は`qc_thresholds.yaml`に置き、コードへ埋め込まない。

## 10.4 テキストQCフラグ

| フラグ | 条件 |
|---|---|
| `very_short_text` | 評価文字数1以下 |
| `very_long_text` | 評価文字数300超 |
| `low_japanese_ratio` | 日本語文字・ASCII英数字以外が多い |
| `unexpected_control_char` | 改行・タブ以外の制御文字 |
| `repeated_chars` | 同一文字の異常反復 |
| `replacement_char` | `�`を含む |
| `suspicious_markup` | HTML/XMLタグらしき文字列 |
| `digit_heavy` | 数字比率が高い。除外せず数字subsetへ分類 |
| `latin_mixed` | Latin文字を含む。日英混在subsetへ分類 |

## 10.5 duplicate

以下を別々に集計する。

- 同一source ID
- 同一source audio hash
- 同一prepared PCM hash
- 同一raw text
- 同一audio + text
- 同一話者 + 同一text

同一textを別話者が読むことは有益なので除外しない。
同一PCMが複数splitにある場合は重大エラーとする。

## 10.6 ASRを使ったQC

補助的に、2つ以上の独立モデルと正解の差が極端に大きい項目を人手監査候補へ回してよい。

ただし:

- 対象モデル自身の結果を理由に正解データを除外しない。
- 1モデルだけの不一致で除外しない。
- 自動修正しない。
- `asr_disagreement`はflagに留める。

---

# 11. 人手監査

## 11.1 目的

自動QCだけでは次を確認できない。

- 正解テキストと実発話が一致しているか。
- 読み間違い・言い直しが正解に反映されているか。
- 音声が途中で切れていないか。
- 音質が実際に評価可能か。
- 非言語音声のアノテーションが妥当か。

## 11.2 監査規模

### 初回データセット承認

| データセット | 監査件数 |
|---|---:|
| Common Voice | 200 |
| FLEURS | 100 |
| SPREDS-U1 | 100または全件の10%の小さい方ではなく、**大きい方**。上限200 |
| CPJD | 20方言×3件 = 60以上 |
| JVNV | 6感情×10件 = 60以上 |
| JNV | 6感情×5件 = 30以上 |

Common Voiceは次を層化する。

- duration bin
- vote margin
- sentence domain
- age
- gender
- QC flagあり/なし

FLEURSはspeakerとdurationを層化する。

## 11.3 監査ラベル

```text
ok
minor_transcript_issue
major_transcript_mismatch
bad_audio
truncated_audio
wrong_language
unexpected_nonverbal
duplicate
uncertain
```

補助項目:

```text
spoken_text_notes
noise_level: clean / mild / heavy
speech_style: read / spontaneous / acted / nonverbal
reviewer_comment
```

## 11.4 監査UI

追加依存を避け、Python標準ライブラリの`ThreadingHTTPServer`でローカルUIを実装する。

```bash
python -m kotomimi_eval audit create \
  --dataset common_voice_ja_26 \
  --count 200 \
  --seed 20260829

python -m kotomimi_eval audit serve \
  --audit-id common_voice_ja_26-20260829
```

UI要件:

- `<audio controls>`でローカル音声を再生。
- raw referenceとnormalized referenceを表示。
- データセット・sample ID・duration・QC flagを表示。
- キーボードショートカット。
- POSTごとにJSONLへ追記し、ブラウザ終了で失わない。
- 前後移動。
- 未監査・要再確認フィルタ。
- Common Voiceの元`client_id`を表示しない。
- 外部ネットワークへbindせず、既定は`127.0.0.1`。

## 11.5 最低品質の承認基準

初期基準:

- `bad_audio + major_transcript_mismatch + wrong_language`が監査対象の5%以下。
- `truncated_audio`が2%以下。
- 重大問題が連続して同じファイル群・話者・変換経路に偏っていない。
- 監査対象の100%に判定がある。
- `uncertain`は再確認し、最終判定を付ける。

5%は「高品質なゴールドコーパス」の基準ではなく、最低限ベンチマークとして使えるかを判断する初期ゲートである。

監査結果が基準を超えた場合:

- データセット全体を自動排除しない。
- `status=experimental`にする。
- 問題の層を特定する。
- `official`結果は残し、リリースゲートの総合値からは外す。

---

# 12. 決定的サンプリング

`first N`は使用しない。

## 12.1 stable score

```python
score = sha256(f"{seed}\0{sample_id}".encode()).digest()
```

各stratum内でscore順に採用する。

## 12.2 speaker-aware

話者IDがある場合:

1. 同一話者の最大件数を制限する。
2. まず話者をstable hash順に選ぶ。
3. 話者内でsampleをstable hash順に選ぶ。
4. 目標件数までround-robinする。

## 12.3 stratification

Common Voice:

```text
duration_bin × domain × vote_quality × gender × age
```

ただし欠損メタデータを捨てず、`unknown`層として扱う。

CPJD:

```text
dialect × speaker
```

JVNV/JNV:

```text
emotion × speaker × session
```

## 12.4 suite lock

各suite実行時に次を保存する。

```json
{
  "suite": "minimum-strict",
  "suite_version": 1,
  "seed": 20260829,
  "datasets": {
    "common_voice_ja_26": {
      "manifest_sha256": "...",
      "selected_count": 1000,
      "selected_ids_sha256": "..."
    },
    "fleurs_ja": {
      "manifest_sha256": "...",
      "selected_count": 300,
      "selected_ids_sha256": "..."
    }
  }
}
```

選択ID一覧自体はデータ利用条件に配慮して既定でGitへ含めず、hashとアルゴリズムで再現する。

---

# 13. ストリーミング評価データの構築

## 13.1 方針

元データは発話単位へ分割済みである。
VAD・endpoint・preroll・refineの品質を測るため、ローカルで複数クリップを連結する。

生成物:

```text
data/streams/<recipe>/<stream_id>.flac
data/streams/<recipe>/<stream_id>.segments.json
data/streams/<recipe>/<stream_id>.reference.txt
```

Gitへ置くもの:

```text
recipes/streaming_minimum.yaml
```

Gitへ置かないもの:

- 生成FLAC
- 元音声のコピー
- 完全な正解manifest

## 13.2 recipe例

```yaml
schema_version: 1
name: streaming_minimum
seed: 20260829
source_suites:
  - minimum-strict
session_count: 100
session_duration_s:
  min: 60
  max: 180
silence_patterns_ms:
  - 50
  - 150
  - 350
  - 700
  - 2000
weights:
  50: 0.10
  150: 0.20
  350: 0.30
  700: 0.25
  2000: 0.15
speaker_change_probability: 0.35
nonverbal_insert_probability: 0.0
amplitude_jitter_db:
  min: -6
  max: 3
codec_roundtrip: false
```

`streaming_stress`ではJNV/JVNVを挿入してよいが、ライセンスが異なる音声を1ファイルへ混ぜると派生物の条件が複雑になる。
次を守る。

- 1つの生成streamは原則として同一ライセンスpolicy内で作る。
- CC BY-SAの素材を含むstreamは`sharealike`として明示する。
- 生成streamは配布しない。

## 13.3 正解時刻

連結時に各clipの次を保存する。

```json
{
  "sample_id": "...",
  "start_sample": 16000,
  "end_sample": 81234,
  "reference_raw": "...",
  "speaker_id": "...",
  "gap_before_ms": 350
}
```

時刻はfloat秒ではなくsample indexを正とする。

## 13.4 ストリーミング指標

- oracle segmentation CER
- streaming end-to-end CER
- `streaming_penalty = streaming_cer - oracle_cer`
- prefix deletion rate
- suffix deletion rate
- segment merge rate
- segment split rate
- false final rate
- partial revision rate
- time-to-first-text
- finalization latency p50/p95
- refine latency
- JNV挿入区間でのnonempty output rate

---

# 14. 正規化と指標

## 14.1 正規化レベル

### `raw`

元表記に対して文字単位で比較する。
句読点・全半角差も誤りになる。

### `standard`

- Unicode NFKC
- casefold
- 空白除去
- 一般句読点除去
- 制御文字除去
- 連続空白の正規化

次は行わない。

- 漢数字から算用数字への変換
- 同音異義語の正規化
- カタカナからひらがなへの変換
- 読みへの変換
- 意味的な同値判定

### `spoken-form`

数字・単位等の研究用補助指標として将来追加してよいが、初期実装には含めない。

## 14.2 指標

### 全発話

- raw CER
- normalized CER
- sentence exact match
- insertion / deletion / substitution counts
- decode failure count
- RTF
- p50/p95 per-clip latency
- peak RSS

### subset

- duration bin
- dataset
- speaker
- age/gender（自己申告がある場合）
- Common Voice domain
- digit-containing
- Latin-containing
- 方言
- 感情
- QC flag

### 非言語

- nonempty output rate
- output chars per minute
- false final count

## 14.3 集計

次を同時に表示する。

- micro CER: 全文字をまとめたCER
- dataset macro CER: データセットごとのCERを同じ重みで平均
- category macro CER
- speaker bootstrap 95% CI
- speaker IDがない場合はclip bootstrapであることを明記

Common Voiceの件数が多いため、micro CERだけを総合指標にしない。

---

# 15. 評価CLI

```bash
# 利用可能なデータセットとライセンス状態
python -m kotomimi_eval dataset list
python -m kotomimi_eval license check --all

# 取得・import
python -m kotomimi_eval dataset download fleurs_ja
python -m kotomimi_eval dataset import common_voice_ja_26 --archive /path/cv.tar.gz
python -m kotomimi_eval dataset import spreds_u1_ja --archive /path/spreds.zip

# 準備・QC
python -m kotomimi_eval dataset prepare fleurs_ja
python -m kotomimi_eval qc run --dataset fleurs_ja
python -m kotomimi_eval qc report --dataset fleurs_ja --format html

# 人手監査
python -m kotomimi_eval audit create --dataset fleurs_ja --count 100 --seed 20260829
python -m kotomimi_eval audit serve --latest
python -m kotomimi_eval audit report --latest

# suite作成
python -m kotomimi_eval suite build minimum-strict
python -m kotomimi_eval suite verify minimum-strict

# モデル評価
python -m kotomimi_eval evaluate \
  --suite minimum-strict \
  --system hayamimi-ja \
  --threads 6

# ストリーミング生成と評価
python -m kotomimi_eval stream build --recipe recipes/streaming_minimum.yaml
python -m kotomimi_eval evaluate \
  --suite streaming-minimum \
  --system hayamimi-ja \
  --mode streaming

# ベースライン比較
python -m kotomimi_eval compare \
  --baseline artifacts/baselines/reazon-v1/report.json \
  --candidate artifacts/runs/20260829/report.json \
  --fail-on-regression
```

---

# 16. Hayamimiとの接続

既存`RoutedASR`を直接importするadapterを用意する。

```python
class HayamimiAdapter:
    system_id = "hayamimi-ja"

    def transcribe_file(self, path: Path) -> Hypothesis:
        ...

    def transcribe_stream(self, path: Path) -> list[Event]:
        ...
```

## 16.1 offline評価

- 正解区間の音声をそのままASRへ渡す。
- `forced_lang="ja"`を使用する。
- 句読点あり・なしを設定として記録する。
- raw ASR outputとnormalized outputを両方保存する。

## 16.2 streaming評価

既存の`wav_chunks()`、VAD、`run_stream()`を再利用する。
console parsingに依存せず、イベントsinkを注入できるよう最小限のrefactorを行う。

必要なイベント:

```text
partial
final
refine
vad_start
vad_end
session_end
```

各イベントにaudio sample positionを持たせる。

## 16.3 評価データに最適化しすぎない

- 評価splitの正解テキストをhotwordへ入れない。
- 評価結果を見て個別置換辞書を追加しない。
- Common Voice testやFLEURS testを辞書構築に使わない。
- 調整用と最終評価用を分離する。

初期段階では:

```text
public-dev: Common Voice dev + FLEURS validation
public-test: Common Voice test + FLEURS test
private-test: 将来の自前連続音声
```

とする。

---

# 17. 回帰ゲート

## 17.1 フェーズ1: 観測

最初のベースラインが確定するまでは、精度閾値でCIを落とさない。

必須:

- suite hash一致
- すべての音声を処理できる
- レポートschema一致
- NaNなし
- 失敗件数の増加なし

## 17.2 フェーズ2: baseline-relative

baseline確定後の既定案:

- `minimum-strict` normalized micro CERが+0.5ポイントを超えて悪化しない。
- Common VoiceまたはFLEURS単独で+1.0ポイントを超えて悪化しない。
- deletion rateが相対15%以上悪化しない。
- p95 decode latencyが相対20%以上悪化しない。
- peak RSSが相対20%以上増加しない。
- JNV nonempty output rateが+2ポイントを超えて悪化しない。

件数が少ないsubsetはCIゲートにしない。

## 17.3 paired bootstrap

同一sampleのbaseline/candidate差を使い、10,000回のbootstrapを行う。

- 話者IDがある場合はspeaker cluster bootstrap。
- 話者IDがない場合はsample bootstrap。
- seedをレポートへ保存。
- CIとeffect sizeを報告。

閾値だけでなく、95% CIが0をまたぐかを表示する。

---

# 18. レポート

## 18.1 JSON

機械判定の正本。

```json
{
  "schema_version": 1,
  "run_id": "20260829T120000Z-hayamimi-ja-a1b2c3",
  "suite": {
    "name": "minimum-strict",
    "version": 1,
    "lock_sha256": "..."
  },
  "system": {
    "id": "hayamimi-ja",
    "git_commit": "...",
    "model_files": {
      "encoder": "sha256:..."
    }
  },
  "environment": {
    "os": "macOS",
    "cpu": "Apple M3 Pro",
    "threads": 6
  },
  "metrics": {
    "normalized_micro_cer": 0.0,
    "dataset_macro_cer": 0.0,
    "p95_latency_ms": 0.0
  },
  "datasets": {},
  "subsets": {},
  "failures": []
}
```

## 18.2 Markdown

人間向けに次を先頭へ出す。

1. 合否
2. baselineとの差
3. データセット別CER
4. insertion/deletion/substitution
5. 数字・Latin・短音声・長音声
6. JNV誤出力
7. p50/p95 latency、RTF、RSS
8. 利用したデータ版とlicense policy
9. QC・人手監査状態
10. 未実行データセット

## 18.3 HTML

- エラーが大きいsample上位
- baseline/candidate差分
- 音声再生
- reference / hypothesis
- edit alignment
- QC flag

HTMLはローカル利用を前提とし、音声をbase64埋め込みしない。

---

# 19. 依存関係

`requirements-eval.txt`をruntimeと分離する。

候補:

```text
# requirements.txtを先にインストール
pytest
jiwer
datasets[audio]
pyarrow
PyYAML
psutil
```

方針:

- Common Voice API用ライブラリはoptional extraにする。
- `gdown`を必須にしない。
- Web UIのためにStreamlit/Gradioを追加しない。
- 音声変換はffmpegを使用する。
- HTTP取得は標準ライブラリまたは既存`huggingface_hub`を使う。

`pyproject.toml`ではPython `>=3.10,<3.14`等、実際にCI確認した範囲を記載する。
推測で広い範囲を宣言しない。

---

# 20. テスト戦略

## 20.1 常時CI

実データ・ASRモデルなしで実行する。

- YAML schemaとlicense gate
- denied dataset
- archive traversal防止
- synthetic WAVの音声QC
- normalization
- manifest serialization
- stable sampling
- speaker-aware sampling
- duplicate検出
- adapterのfixture archive parsing
- CER/metrics
- bootstrap再現性
- regression gate
- streaming recipeの時刻計算

## 20.2 データあり統合テスト

環境変数で有効化する。

```text
KOTOMIMI_EVAL_DATA_ROOT
KOTOMIMI_RUN_DATASET_TESTS=1
```

- 期待件数
- 全ファイル存在
- manifest hash
- 100件のdecode smoke
- QC report生成

## 20.3 モデルあり統合テスト

```text
KOTOMIMI_RUN_MODEL_EVAL=1
```

- smoke suite
- minimum suite
- result schema
- baseline compare

## 20.4 ネットワークテスト

通常CIでは行わない。

- FLEURS download
- MDC API download

定期手動workflowまたは開発者ローカルで行う。

---

# 21. 実装PR計画

一度に全て実装しない。

## PR E0 — 骨格・ライセンスゲート・schema

### 目的

データを取得する前に、採用可能条件をコードで固定する。

### 実装

- ディレクトリ骨格
- `datasets.yaml`
- `suites.yaml`
- `denied_datasets.yaml`
- dataclass / schema
- license policy
- manual approval
- CLI `dataset list` / `license check`
- gitignore
- unit tests

### 受け入れ条件

- NC、research-only、Article 30-4 onlyが必ず拒否される。
- Common Voice、FLEURS、SPREDSが`strict`として通る。
- CPJD/JVNV/JNVが`sharealike`を明示しないsuiteでは拒否される。
- ITA-Rionがapprovalなしでは拒否される。
- 実音声を使わず全テストが通る。

## PR E1 — FLEURS adapter

### 目的

最も取得・固定しやすいデータでend-to-end基盤を完成させる。

### 実装

- pinned revision download
- `ja_jp/test`
- 650件検証
- 16kHz FLAC変換
- manifest
- basic QC
- `minimum-fleurs` suite
- offline evaluation
- JSON/Markdown report

### 受け入れ条件

- 650件以外なら停止。
- 同じrevisionと環境でmanifest hashが再現する。
- 全件decode可能。
- CER結果が既存`eval_common.py`と小さなfixtureで一致する。

## PR E2 — Common Voice adapter

### 実装

- archive import
- MDC API optional downloader
- `test.tsv`限定
- 9,020件検証
- speaker ID秘匿化
- vote/domain/age/gender metadata
- no re-host警告
- deterministic sampler

### 受け入れ条件

- 生音声・manifest・client_idがGitへ追加されない。
- test以外を誤って混ぜない。
- 期待件数・欠損音声を検証。
- 同じseedで同じ1,000件を選ぶ。

## PR E3 — QCと監査UI

### 実装

- audio/text/duplicate QC
- official/clean view
- audit sample生成
- localhost audit server
- audit JSONL
- QC HTML/Markdown

### 受け入れ条件

- QCで元referenceを変更しない。
- flagだけの項目をofficial viewから除外しない。
- audit結果が途中で失われない。
- `127.0.0.1`以外へ既定bindしない。

## PR E4 — `minimum-strict`とbaseline

### 実装

- suite builder
- Common Voice 1,000 + FLEURS 300
- suite lock
- Hayamimi offline adapter
- bootstrap CI
- baseline report

### 受け入れ条件

- first Nを使わない。
- Common Voiceに単一話者が偏らない。
- dataset macroを出す。
- baselineのgit commit・model hash・suite hashを保存。

## PR E5 — SPREDS-U1 manual adapter

### 実装

- archive import
- format detection
- Japanese subset extraction
- attribution
- `minimum-strict-spreds`
- fixture archive tests

### 受け入れ条件

- 複数の日本語候補がある場合に勝手に選ばない。
- SPREDSがなくても他suiteは動く。
- manual acquisition手順をREADMEへ記載。

## PR E6 — CPJD / JVNV / JNV

### 実装

- 各adapter
- license policy伝播
- dialect/emotion/nonverbal metadata
- `minimum-extended`
- JNV専用指標

### 受け入れ条件

- `--allow-sharealike`なしでは実行しない。
- JNVをCERへ混ぜない。
- CPJDを20方言で均等抽出できる。
- JVNVを感情・話者で層化できる。

## PR E7 — streaming recipe

### 実装

- deterministic stream composer
- sample-index annotation
- silence patterns
- oracle vs streaming evaluator
- boundary metrics
- local-only generated files

### 受け入れ条件

- 同じmanifest/seedでPCM hashが一致。
- 正解時刻に丸め誤差がない。
- 生成streamをGitへ追加しない。
- 同一streamのlicense policyを追跡できる。

## PR E8 — 回帰ゲート・比較UI

### 実装

- paired compare
- cluster bootstrap
- threshold policy
- JSON/Markdown/HTML差分
- exit code

### 受け入れ条件

- suite hashが違う比較を拒否する。
- sample欠損を黙って無視しない。
- 精度、速度、メモリ、JNV誤出力を別々に判定。

## PR E9 — ITA-Corpus-Rion optional adapter

### 実装

- approval gate
- local archive import
- transcript mapping
- age/gender strata
- no-resale attribution note

### 受け入れ条件

- approvalなしで実行不能。
- download formを自動操作しない。
- 出力レポートへ追加条件を表示。

---

# 22. PR E0をCodexへ渡す最初のプロンプト

```text
このリポジトリに、商用利用可能・無償の日本語ASR評価データ基盤のPR E0だけを実装してください。

参照文書:
- commercial_ja_asr_eval_dataset_codex_plan.md
- japanese_asr_codex_development_plan.md

今回のスコープ:
1. benchmarks/ja_eval のディレクトリ骨格を作る。
2. config/datasets.yaml、suites.yaml、denied_datasets.yamlを作る。
3. strict / sharealike / manual-review のライセンスポリシーを実装する。
4. unknown、NC、research-only、Article 30-4 onlyをfail-closedで拒否する。
5. manual-reviewはローカルapproval JSONがなければ拒否する。
6. dataset list と license check のCLIを実装する。
7. schemaとモデル不要unit testを追加する。
8. raw audioやdataset archiveをGitへ追加しない.gitignoreを更新する。

今回実装しないもの:
- データのダウンロード
- FLEURS/Common Voice adapter
- 音声変換
- ASR評価
- 人手監査UI
- streaming生成
- 既存ASRランタイムの変更

実装前に確認すること:
- 現在のリポジトリ構成
- Pythonとpytestの既存方針
- LICENSEとTHIRD_PARTY_NOTICES.md
- requirements-dev.txt

完了時に報告すること:
1. 変更概要
2. 変更ファイル一覧
3. 実行したコマンド
4. テスト結果
5. fail-closedのテストケース一覧
6. 次のPR E1で必要な課題

計画外の機能は追加しないでください。
```

---

# 23. PR E1をCodexへ渡すプロンプト

```text
PR E0が完了済みの状態で、PR E1（FLEURS adapter）だけを実装してください。

必須条件:
- source: google/fleurs
- config: ja_jp
- split: test
- revision: 70bb2e84b976b7e960aa89f1c648e09c59f894dd
- license: CC-BY-4.0
- expected rows: 650

実装内容:
1. pinned revisionからFLEURS Japanese testを取得するadapter。
2. source sample IDを維持する。
3. 16kHz mono FLACへ変換する。音量正規化とtrimはしない。
4. source/prepared audioのSHA-256を記録する。
5. 統一JSONL manifestとdataset.lock.jsonを作る。
6. 破損、欠損、空referenceをhard failureにする。
7. basic QC flagを作るが、自動除外しない。
8. minimum-fleurs suiteとoffline評価を実装する。
9. JSONとMarkdownのレポートを作る。
10. 実データなしのfixture testと、データありのoptional integration testを追加する。

禁止:
- revision省略
- first Nだけを正式なminimum suiteにすること
- referenceを書き換えること
- FLEURS以外のadapterを同じPRへ追加すること
- 実音声をGitへコミットすること

完了時に、650件確認、manifest hash、QC件数、評価コマンド、未解決事項を報告してください。
```

---

# 24. 各PR後の共通レビュー指示

```text
今回の変更を自己レビューしてください。

確認項目:
- 商用利用不可・条件不明データを通す経路がないか。
- license policyがfail-openになっていないか。
- raw audio、archive、speaker identifier、approvalファイルをGitへ追加していないか。
- source revision、split、件数、hashを固定しているか。
- reference_rawを失っていないか。
- official viewをASR結果で都合よくfilterしていないか。
- first N samplingをしていないか。
- 同じseedで同じsubsetになるか。
- Windows/macOS/Linuxのパスを考慮しているか。
- archive extractionにpath traversalがないか。
- ffmpegをshell=Trueで呼んでいないか。
- suite hashが違う結果を比較していないか。
- dataset macroとmicroを混同していないか。
- JNVをCERへ混ぜていないか。
- streaming生成物をGitへ入れていないか。

問題があれば修正し、以下を報告してください。
1. 変更概要
2. テスト結果
3. データ版・件数・manifest hash
4. ライセンス判定
5. QC結果
6. 実行できなかった検証
7. 残るリスク
```

---

# 25. 最初のベースライン確定手順

実装完了後、次の順で進める。

## 25.1 FLEURS

```bash
python -m kotomimi_eval dataset download fleurs_ja
python -m kotomimi_eval dataset prepare fleurs_ja
python -m kotomimi_eval qc run --dataset fleurs_ja
python -m kotomimi_eval audit create --dataset fleurs_ja --count 100 --seed 20260829
python -m kotomimi_eval audit serve --latest
```

監査が完了し、基準内なら`approved_for_gate=true`をローカルstatusへ記録する。

## 25.2 Common Voice

```bash
python -m kotomimi_eval dataset import common_voice_ja_26 --archive "$CV_ARCHIVE"
python -m kotomimi_eval dataset prepare common_voice_ja_26
python -m kotomimi_eval qc run --dataset common_voice_ja_26
python -m kotomimi_eval audit create --dataset common_voice_ja_26 --count 200 --seed 20260829
python -m kotomimi_eval audit serve --latest
```

## 25.3 minimum suite

```bash
python -m kotomimi_eval suite build minimum-strict
python -m kotomimi_eval suite verify minimum-strict
python -m kotomimi_eval evaluate --suite minimum-strict --system hayamimi-ja
```

## 25.4 baseline登録

baselineは人手で承認する。

```bash
python -m kotomimi_eval baseline approve \
  --run artifacts/runs/<RUN_ID>/report.json \
  --name hayamimi-ja-initial
```

自動的に最新runをbaselineへ昇格しない。

---

# 26. 完了条件

次を全て満たした時点で、最低限の評価データ基盤が完成したと判断する。

- Common Voice 26.0 Japanese test 9,020件を再現可能に準備できる。
- FLEURS Japanese test 650件をpinned revisionで準備できる。
- `minimum-strict`が同一seedで同じ1,300件になる。
- データ取得元、版、split、license、hashを追跡できる。
- 生データをGitへ再配布しない。
- corrupt/missing/empty referenceを検出できる。
- audio/text/duplicate QCをレポートできる。
- Common Voice 200件、FLEURS 100件の人手監査を保存できる。
- normalized CER、dataset macro CER、速度、メモリを出せる。
- baselineとの差をpaired comparisonできる。
- `streaming-minimum`でoracleとend-to-endの差を測れる。
- CPJD/JVNV/JNVを`sharealike`として明示的に追加できる。
- 商用利用不可データをlicense gateが拒否する。

---

# 27. 実装の優先順位

```text
PR E0  ライセンス・schema
  ↓
PR E1  FLEURS 650件でend-to-end完成
  ↓
PR E2  Common Voice 9,020件
  ↓
PR E3  QC・人手監査
  ↓
PR E4  minimum-strict・初期baseline
  ↓
PR E5  SPREDS-U1
  ↓
PR E6  方言・感情・非言語
  ↓
PR E7  streaming評価
  ↓
PR E8  回帰ゲート
  ↓
PR E9  ITA-Corpus-Rion（必要な場合のみ）
```

最初の実用ラインはPR E4までである。
SPREDS-U1やCC BY-SAの追加セットが未取得でも、Common Voice + FLEURSで最低限の品質確認を開始できる。

---

# 28. 参照情報

以下は2026-08-29時点で確認した公式または提供元の情報である。
実装時には各ページを再確認し、変更があればCodexが勝手に追従せず、registry更新PRとして扱う。

## 採用

- Common Voice Scripted Speech 26.0 - Japanese  
  https://mozilladatacollective.com/datasets/cmqim4lxy00tunr07cjkcupeg

- Mozilla Data Collective API  
  https://mozilladatacollective.com/api-reference

- Google FLEURS  
  https://huggingface.co/datasets/google/fleurs

- FLEURS publication  
  https://research.google/pubs/fleurs-few-shot-learning-evaluation-of-universal-representations-of-speech/

- SPREDS-U1 metadata  
  https://nict.repo.nii.ac.jp/records/2000207  
  https://cir.nii.ac.jp/crid/1510304869612386688

- CPJD  
  https://sites.google.com/site/shinnosuketakamichi/research-topics/cpjd_corpus

- JVNV  
  https://sites.google.com/site/shinnosuketakamichi/research-topics/jvnv_corpus

- JNV  
  https://sites.google.com/site/shinnosuketakamichi/research-topics/jnv_corpus

- ITA-Corpus-Rion  
  https://github.com/Rion-Dev/ita-corpus-Rion

- ITA Corpus text  
  https://github.com/mmorise/ita-corpus

## 不採用条件の確認

- ReazonSpeech dataset  
  https://huggingface.co/datasets/reazon-research/reazonspeech

- JSUT  
  https://sites.google.com/site/shinnosuketakamichi/publication/jsut

- JVS  
  https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_corpus

- JECS  
  https://sites.google.com/site/shinnosuketakamichi/research-topics/jecs_corpus

- J-CHAT  
  https://huggingface.co/datasets/sarulab-speech/J-CHAT

---

# 29. 最終判断

無料・商用利用可能・最低限の品質確認という条件では、最初から大量の候補を混ぜるべきではない。

既定構成は次とする。

```text
Common Voice Japanese 26.0 test
  +
FLEURS ja_jp test
```

この2つで、次を確保する。

- 1万件近い多話者・多環境の読み上げ評価
- 650件の固定された標準ベンチマーク
- CC0 / CC BY 4.0の商用利用可能な条件
- vote metadataと人手監査による最低限の品質確認
- 再現可能な版・split・hash

その後、用途に応じて次を追加する。

```text
SPREDS-U1       統制された音声認識評価
CPJD            方言
JVNV            感情 + 非言語
JNV             非言語での誤出力
ITA-Corpus-Rion 統制された多数話者音声（条件確認後）
```

特に重要なのは、データセット名よりも、**公式splitを固定し、ライセンスをfail-closedで管理し、機械QCと人手監査の結果を保存すること**である。
