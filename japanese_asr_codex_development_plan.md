# 日本語特化リアルタイムASR 開発計画

> Codex向け実装仕様書  
> 対象: `oboroge0/hayamimi` をベースにした日本語特化版  
> 基準リビジョン: `acc46cc2d6a10e4d29caa00469f30e5ad2caf307`（`main`、2026-08-29確認）  
> 作業名: **Kotomimi（仮）**  
> 最終更新: 2026-08-29

---

## 0. この文書の使い方

この文書は、Codexにリポジトリを編集させるための実装計画兼タスク仕様である。
一度に全機能を実装せず、後述する **PR 0 → PR 1 → …** の順番で進める。

Codexは各PRで、次のサイクルを必ず守ること。

1. 対象コードと関連ドキュメントを読む。
2. 変更前のテストとベンチマークを記録する。
3. 小さな変更として実装する。
4. モデル不要のテストを実行する。
5. モデルがある環境では日本語評価を実行する。
6. 変更前後の数値と未解決事項を報告する。
7. 受け入れ条件を満たさない場合、機能フラグを既定で無効にする。

モデルファイル、評価音声、個人情報をGitへコミットしてはならない。

---

# 1. プロジェクト名候補

## 1.1 推奨候補

| 優先 | 表記 | リポジトリ名候補 | 意味・印象 | 向いている使い方 |
|---:|---|---|---|---|
| 1 | **Kotomimi / ことみみ** | `kotomimi` | 「ことばを聞き取る耳」。柔らかいがASRらしさもある | 独立した新プロジェクト・製品名 |
| 2 | **Hayamimi-JA / 早耳JA** | `hayamimi-ja` | 元プロジェクトとの関係が最も明確 | hayamimiの派生・フォークとして公開 |
| 3 | **Mimikoto / みみこと** | `mimikoto` | 「耳」と「ことば／こと」を組み合わせた造語 | 独自ブランド、内部コード名 |
| 4 | **MimiKana / みみかな** | `mimikana` | 耳＋仮名。親しみやすく日本語感が強い | GUIアプリ、一般ユーザー向け |
| 5 | **Kikuji / 聞く字** | `kikuji` | 音声を「字」にする機能を短く表現 | CLI・開発者向けツール |
| 6 | **HayaMoji / 早文字** | `hayamoji` | 高速な文字起こしを直感的に表現 | 速度を前面に出す派生プロジェクト |

### 推奨判断

- **hayamimiのコードを大きく残すフォーク**として公開するなら、`Hayamimi-JA` が最も誤解が少ない。
- **独立した日本語ASR製品**として育てるなら、`Kotomimi` を推奨する。
- 本文では作業名として `Kotomimi` を使うが、コード上では名称を定数やパッケージ名に早期に埋め込まない。

### 名前の重複に関する注意

2026-08-29時点のGitHubリポジトリ名の簡易検索では、`kotomimi`、`hayamimi-ja`、`mimikoto`、`mimikana`、`hayamoji` の完全一致リポジトリは見つからなかった。`kikuji`も完全一致は見つからなかったが、`Kikujiro`を含む名称は存在する。
これは商標、PyPI、npm、ドメイン、App Storeの確認ではない。名称決定前に別途確認すること。

---

# 2. エレベーターピッチ

**Kotomimiは、クラウドを使わずCPUだけで動作し、日本語の自然会話、固有名詞、日英混在、数字、VAD境界に強いリアルタイム音声認識エンジンである。**

hayamimiのReazonSpeech + sherpa-onnxという高速な基盤を活かしながら、多言語ルーティングではなく日本語にリソースを集中する。
高速な第1段認識と、低品質区間だけを対象にした選択的再認識を組み合わせる。

---

# 3. 現状認識

## 3.1 現在の日本語経路

対象リビジョンでは、主に次の処理が行われている。

```text
音声入力
  ↓
Silero VAD
  ├─ min_silence: 0.35秒
  ├─ max_speech: 12秒
  └─ PREROLL: 1.0秒
  ↓
RoutedASR
  ├─ 通常: Whisper tiny + SenseVoiceで言語判定
  └─ --mode single --lang ja: 日本語固定
  ↓
ReazonSpeech Zipformer INT8
  └─ modified_beam_search
  ↓
単純な文字列置換
  ↓
日本語句読点復元
  ↓
高速確定
  ↓
2秒程度の無音後にRefinerが発話群をまとめて再認識
```

関連ファイル:

- `scripts/asr_engine.py`
- `scripts/realtime_transcribe.py`
- `scripts/download_models.py`
- `scripts/punct_ja.py`
- `scripts/eval_accuracy.py`
- `scripts/eval_engine.py`
- `scripts/make_realset.py`
- `tests/test_units.py`
- `docs/BENCHMARKS.md`
- `docs/EVAL_REAL.md`
- `docs/LID.md`
- `docs/PUNCT_JA.md`

## 3.2 既に実装済みで、新規実装し直さないもの

`--mode single --lang ja` による固定言語ルートは既に存在する。
そのため「言語判定を外す機能」をゼロから追加する必要はない。

ただし、対象コードでは `forced_lang` が設定されていても、`RoutedASR.__init__()` がLIDモデルを構築し、既定の `preload=True` によって他言語モデルのプリロードも開始する。
日本語専用モードとしては余分なので、真に日本語だけをロードするように修正する。

## 3.3 主な問題

### A. VAD経路で認識精度が落ちる

既存資料では、音声全体を一括認識した場合と、実際のVAD経路を通した場合に大きな差がある。
これは基盤モデルだけでなく、次の要因が影響している可能性が高い。

- 語頭や語尾がVAD境界で欠ける。
- `AudioHistory.last_seg_end` が前セグメントとの重複を完全に禁止する。
- 発話が複数セグメントに分割され、前後文脈が失われる。
- 同じReazonSpeechでも入力窓が短いと同音異義語や固有名詞を誤る。
- Refinerは改善に寄与するが、高速確定側の誤りは一度ユーザーに表示される。

### B. 固有名詞バイアスが日本語で機能しない

現在の `--hotwords` は `modeling_unit="cjkchar"` を指定するが、ReazonSpeech側の `tokens.txt` はbyte-level BPEとして扱われており、ホットワードを符号化できない。
コードはこの状態を検知して警告するが、認識精度は上がらない。

### C. ユーザー辞書が単純な `str.replace`

現在の置換は、文脈、読み、形態素境界を考慮しない。
部分文字列の意図しない置換、同音異義語の誤補正、短い一般語の過剰置換が起こり得る。

### D. 結果に品質判断材料が少ない

`RoutedASR.transcribe()` の返却値は主に次の情報だけである。

```python
{
    "text": str,
    "lang": str,
    "tier": str,
    "lid_ms": float,
    "decode_ms": float,
    "probe_ms": float,
}
```

トークン、タイムスタンプ、反復率、文字密度、境界リスク、候補間不一致などを保持していないため、「どの区間だけ再認識するか」を適切に判断しにくい。

### E. 評価セットが小さく、ストリーミング固有の誤りを分離できない

既存の実音声評価は有用だが、小規模で、放送音声中心である。
自然会話、PC内蔵マイク、遠距離、BGM、固有名詞、数字、日英混在を分けて測る必要がある。

---

# 4. 開発目標

## 4.1 機能目標

1. 日本語専用時にはLIDと他言語ASRをロードしない。
2. VAD境界に前後コンテキストを付けても、重複文字を安全に除去できる。
3. 認識結果にraw、表示用、正規化後、品質シグナルを保持する。
4. 固有名詞辞書を読みと形態素境界に基づいて適用する。
5. 日本語hotwordが実装可能かを再現可能なツールで検証する。
6. 低品質区間だけ、第2モデルまたは高精度設定で再認識できる。
7. 数字、単位、日付、バージョンを壊さない。
8. すべての高度機能を機能フラグで無効化できる。
9. 元のhayamimiの多言語モードを、少なくともMVP期間中は壊さない。

## 4.2 性能目標

数値は固定の絶対値だけで判定せず、同じマシン、同じ音声、同じコミット条件でベースライン比較する。

### MVPの受け入れ目標

- 日本語ストリーミングCERをベースラインから **相対15%以上改善**する。
- VAD境界に起因する先頭・末尾の欠落件数を **30%以上削減**する。
- 固有名詞評価セットでterm recallを **20ポイント以上改善**する。
- 固有名詞の誤挿入率を **1%以下**に保つ。
- p95高速確定遅延をベースラインの **1.25倍以内**に保つ。
- 第2モデルを呼ぶ区間を通常評価セットの **20%以下**に抑える。
- 日本語高速モードの常駐メモリをベースライン以下にする。
- 既存のモデル不要テストをすべて通す。

### ストレッチ目標

- 既存の一括認識とVAD認識のCER差を半分以下にする。
- 日本語高速モードでp50確定遅延150ms以下を維持する。
- 日英混在文の固有名詞完全一致率80%以上。
- 数字・型番・日付の完全一致率95%以上。

## 4.3 非目標

MVPでは次を実装対象にしない。

- 完全な話者分離。
- すべての方言への最適化。
- クラウドAPIを必須にする構成。
- LLMによる自由な文章の書き換え。
- 認識内容に存在しない語を生成する「読みやすさ優先」の補正。
- 既存多言語機能の全面削除。
- 学習済みASRをゼロから新規訓練すること。

---

# 5. 設計原則

## 5.1 音声由来のraw結果を必ず保持する

後処理で表記を変えても、元のASR出力を失わない。

```json
{
  "raw_text": "ごじゅうぎがばいとのめもり",
  "display_text": "50GBのメモリ",
  "normalized_text": "50GBのメモリ"
}
```

## 5.2 「confidence」という名前を安易に使わない

モデルの確率が取得できず、校正もしていない値をconfidenceと呼ばない。
MVPでは `risk_score` と `risk_reasons` を使う。
校正用データでECE等を評価した後にのみ `confidence` を公開する。

## 5.3 音声境界の修復と文字列補正を分離する

- 音声窓をどう作るか。
- 重複するテキストをどう統合するか。
- 固有名詞をどう補正するか。
- 第2モデルをいつ呼ぶか。

これらを1つの巨大関数に入れない。

## 5.4 既定動作は保守的にする

候補の優劣を判断できない場合、長くて流暢な文章ではなく、元の高速認識を採用する。
数字を壊す可能性がある候補は棄却する。

## 5.5 評価不能な最適化は入れない

各最適化には次のいずれかが必要である。

- 単体テスト。
- A/Bベンチマーク。
- 実音声の失敗例と修正後の再現結果。

---

# 6. 目標アーキテクチャ

```text
16kHz mono PCM
  ↓
Silero VAD
  ↓
SegmentWindowBuilder
  ├─ speech_start / speech_end
  ├─ context_start / context_end
  ├─ pre-context
  ├─ post-context
  └─ controlled overlap
  ↓
PrimaryJapaneseASR
  └─ ReazonSpeech Zipformer INT8 / modified beam
  ↓
RawDecodeResult
  ├─ raw text
  ├─ optional tokens
  ├─ optional timestamps
  ├─ decode time
  └─ model metadata
  ↓
BoundaryTextMerger
  ├─ timestamp alignment if available
  └─ Japanese-character fuzzy alignment fallback
  ↓
JapanesePostProcessor
  ├─ Unicode normalization
  ├─ conservative lexicon correction
  ├─ punctuation
  └─ deterministic ITN
  ↓
QualityGate
  ├─ boundary risk
  ├─ repetition
  ├─ characters/sec
  ├─ unexpected Latin ratio
  ├─ digit preservation
  └─ primary/refine disagreement
  ↓
              ┌──────── risk low ────────┐
              │                          ▼
              │                    final result
              │
              └──────── risk high
                         ↓
                 SecondaryJapaneseASR
                 ├─ high-precision Reazon profile
                 ├─ Qwen3-ASR 0.6B INT8 candidate
                 └─ other benchmarked backend
                         ↓
                 ConservativeCandidateSelector
                         ↓
                    final result
```

---

# 7. 推奨ファイル構成

MVPでは既存コードを大きく移動しすぎない。
新しい純粋ロジックを小さなモジュールとして追加する。

```text
scripts/
  asr_engine.py                    # 既存。多言語ルートを維持
  realtime_transcribe.py           # 既存。パイプライン統合
  download_models.py               # 既存。日本語専用モデルセットを追加

  japanese_types.py                # 新規: dataclass / TypedDict
  segment_window.py                # 新規: 音声窓と境界コンテキスト
  text_overlap.py                  # 新規: 重複文字列の安全な統合
  japanese_lexicon.py              # 新規: 読み・形態素境界ベース辞書
  japanese_normalizer.py           # 新規: rawを保持する決定的正規化
  quality_gate.py                  # 新規: risk signals
  secondary_asr.py                 # 新規: 第2ASRのProtocolと実装
  candidate_selector.py            # 新規: 候補比較
  inspect_reazon_model.py          # 新規: tokens/metadata/hotword調査
  eval_ja_streaming.py             # 新規: ストリーミング評価

configs/
  japanese.default.json            # 新規: 実験値をコードから分離
  lexicon.example.jsonl            # 新規: 固有名詞辞書の例

 tests/
  test_segment_window.py
  test_text_overlap.py
  test_japanese_lexicon.py
  test_japanese_normalizer.py
  test_quality_gate.py
  test_candidate_selector.py
  test_japanese_profile.py

 docs/
  JA_BASELINE.md
  JA_ARCHITECTURE.md
  JA_EVALUATION.md
  JA_HOTWORDS.md
```

新しいランタイム依存は、明確な改善が確認されるまで増やさない。
`fugashi`と`unidic-lite`は既にrequirementsに含まれているため、読み取得に再利用する。

---

# 8. データ構造

## 8.1 AudioWindow

```python
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class AudioWindow:
    samples: np.ndarray
    sample_rate: int
    speech_start: int
    speech_end: int
    context_start: int
    context_end: int
    overlap_with_previous_samples: int
    forced_split: bool = False

    @property
    def speech_duration_s(self) -> float:
        return (self.speech_end - self.speech_start) / self.sample_rate
```

## 8.2 DecodeResult

```python
from dataclasses import dataclass, field


@dataclass
class DecodeResult:
    raw_text: str
    model_id: str
    decode_ms: float
    tokens: list[str] = field(default_factory=list)
    token_ids: list[int] = field(default_factory=list)
    timestamps_s: list[float] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
```

sherpa-onnxの結果がtokensやtimestampsを返さない場合は空配列にする。
存在しない情報を推測して埋めない。

## 8.3 RiskReport

```python
from dataclasses import dataclass, field


@dataclass
class RiskReport:
    score: float
    reasons: list[str] = field(default_factory=list)
    signals: dict[str, float | int | bool | str] = field(default_factory=dict)
```

## 8.4 TranscriptionResult

```python
@dataclass
class TranscriptionResult:
    raw_text: str
    display_text: str
    normalized_text: str
    language: str
    model_id: str
    tier: str
    decode_ms: float
    risk: RiskReport
    is_refined: bool = False
    secondary_used: bool = False
```

既存コードとの互換性のため、最初は `to_legacy_dict()` または辞書変換を用意する。
一度に全呼び出し元を壊さない。

## 8.5 LexiconEntry

JSONL例:

```json
{"surface":"ReazonSpeech","readings":["りーぞんすぴーち","りーざんすぴーち"],"aliases":["リーゾンスピーチ"],"weight":2.5,"domains":["asr"],"safe":true}
{"surface":"多摩センター","readings":["たませんたー"],"aliases":[],"weight":2.0,"domains":["place"],"safe":true}
{"surface":"Qwen3-ASR","readings":["くうぇんすりーえーえすあーる","きゅーうぇんすりーえーえすあーる"],"aliases":["Qwen 3 ASR"],"weight":2.5,"domains":["asr"],"safe":true}
```

`safe=false` の読みベース補正は自動適用せず、候補スコアだけに使う。

---

# 9. PR単位の実装計画

---

## PR 0: ベースライン固定と評価基盤

### 目的

コードの振る舞いを変える前に、現状の日本語精度、遅延、メモリ、境界エラーを再現可能にする。

### 変更対象

- 新規 `scripts/eval_ja_streaming.py`
- 新規 `docs/JA_BASELINE.md`
- 必要に応じて `scripts/eval_common.py`
- 必要に応じて `scripts/make_realset.py`
- 新規モデル不要テスト

### 実装内容

#### 1. 評価manifest

JSONLを使う。

```json
{"id":"ja_clean_001","wav":"testdata/eval_ja/ja_clean_001.wav","text":"今日は東京都多摩市で会議をします。","category":"clean","terms":["東京都多摩市"],"digits":[]}
```

必須フィールド:

- `id`
- `wav`
- `text`
- `category`

任意フィールド:

- `terms`
- `digits`
- `speaker_group`
- `license_source`
- `notes`

#### 2. 4経路を測る

- `offline_primary`: 発話全体をReazonSpeechへ渡す。
- `stream_fast`: 実際のVAD、高速確定のみ。
- `stream_refine`: VAD + Refiner。
- `stream_single_ja`: `--mode single --lang ja` と等価の経路。

#### 3. 出力

機械可読JSONとMarkdownを両方生成する。

```text
artifacts/ja_eval/<timestamp>/metrics.json
artifacts/ja_eval/<timestamp>/report.md
artifacts/ja_eval/<timestamp>/hypotheses.jsonl
```

`artifacts/` は `.gitignore` に追加する。

#### 4. 指標

- CER
- insertions / deletions / substitutions
- 語頭欠落件数
- 語尾欠落件数
- term recall / precision / F1
- 数字完全一致率
- RTF
- p50 / p95 decode latency
- p50 / p95 final latency
- 最大RSS
- 空文字率
- 異常反復率

#### 5. 評価カテゴリ

最低限、次を分ける。

- `broadcast`
- `clean_mic`
- `conversation`
- `far_field`
- `noise`
- `bgm`
- `short_utterance`
- `proper_noun`
- `numbers`
- `ja_en_mixed`
- `long_speech`

ライセンス上コミットできない音声はmanifestテンプレートと生成スクリプトだけをコミットする。

### テスト

- CER計算の既知ケース。
- term recall計算。
- 数字一致判定。
- JSONL読み込みエラー。
- 空データセット時の明示的エラー。

### 受け入れ条件

- 本PRでは認識結果を変えない。
- `pytest tests -q` が成功する。
- 同じ音声と設定でmetrics.jsonが再現可能である。
- ベースコミットの結果を `docs/JA_BASELINE.md` に記録する。
- マシン、OS、Python、sherpa-onnx、モデルSHAまたはモデルディレクトリ名を記録する。

### CodexへのPR 0指示

```text
まずPR 0だけを実装してください。認識ロジックは変更しないでください。
日本語のoffline / VAD fast / VAD refineを同一manifestから評価できる
scripts/eval_ja_streaming.pyを追加し、JSONとMarkdownのレポートを生成してください。
既存の正規化関数を再利用し、重複実装は避けてください。
モデルがないCIでは評価テストをskipし、指標計算の単体テストは必ず実行してください。
```

---

## PR 1: 真の日本語専用プロファイル

### 目的

既存の `--mode single --lang ja` を、LID・SenseVoice・他言語モデルをロードしない本当の日本語専用モードにする。

### 現状の注意点

`forced_lang` が指定されても、対象リビジョンの `RoutedASR.__init__()` は次を実行する。

- `self.lid = _build_lid(threads)`
- warmup時のLID実行
- `preload=True` なら `_preload_rest()` で他言語モデルをロード

呼び出し時のLIDは回避できているが、モデル構築とプリロードは回避できていない。

### 変更対象

- `scripts/asr_engine.py`
- `scripts/realtime_transcribe.py`
- `scripts/download_models.py`
- `tests/test_japanese_profile.py`
- `README.ja.md`
- `THIRD_PARTY_NOTICES.md` はモデル追加時のみ

### 実装内容

#### 1. LIDの遅延構築または無効化

```python
self.lid = None if forced_lang is not None else _build_lid(threads)
```

`_identify_lang()` は `self.lid is None` の場合に暗黙動作をせず、明示的に例外を出す。
ただし `forced_lang` 経路から呼ばれないことをテストする。

#### 2. 日本語固定時のプリロード停止

`realtime_transcribe.py` から `RoutedASR` を生成するとき、single modeでは `preload=False` を渡す。
さらに `RoutedASR` 側でも、`forced_lang` がある場合に多言語プリロードを開始しない防御を入れる。

#### 3. warmup対象を日本語モデルだけにする

- ReazonSpeechのみwarmup。
- 句読点は設定に応じて遅延ロードまたはバックグラウンドロード。
- Whisper tinyはロードしない。

#### 4. 日本語専用ダウンロードセット

`download_models.py` に次を追加する。

```bash
python scripts/download_models.py --japanese-only
```

含めるもの:

- ReazonSpeech Zipformer
- Silero VAD
- 日本語句読点モデル（`--no-punctuation-model` で省略可能でもよい）

含めないもの:

- Whisper tiny LID
- SenseVoice
- Paraformer zh
- Parakeet multilingual
- Omnilingual
- 翻訳モデル
- 話者モデル

`--minimal` の既存意味は互換性のため維持する。

#### 5. 起動ログ

起動時に次を一度だけ出す。

```text
profile=japanese forced_lang=ja lid=disabled preload=rz-only
```

### テスト

モックを使い、モデル実体なしで次を確認する。

- `forced_lang="ja"` で `_build_lid` が呼ばれない。
- `_preload_rest` が呼ばれない。
- `partial()` と `transcribe()` が `_identify_lang` を呼ばない。
- resident modelが`rz`だけである。
- 通常balanced modeの振る舞いは変わらない。
- CLIで `--mode single` かつ `--lang` なしは従来どおりエラー。

### 受け入れ条件

- 日本語固定モードの起動時RSSが現状以下。
- Whisper tinyがなくても日本語固定モードが起動する。
- balanced modeの既存テストをすべて通す。
- 日本語offline CERがPR 0ベースラインから悪化しない。

### CodexへのPR 1指示

```text
PR 1だけを実装してください。
既存の --mode single --lang ja を再利用し、別の重複した日本語モードは追加しないでください。
forced_langが設定されている場合、LIDモデルと他言語ASRを構築・プリロードしないようにしてください。
既存balanced/fastモードとの互換性を維持し、モックを用いた回帰テストを追加してください。
```

---

## PR 2: VAD境界コンテキストと重複統合

### 目的

VADによる語頭・語尾欠落と文脈分断を減らす。
音声窓を意図的に重複させ、認識テキスト側で安全に重複を除去する。

### 変更対象

- 新規 `scripts/segment_window.py`
- 新規 `scripts/text_overlap.py`
- `scripts/realtime_transcribe.py`
- `tests/test_segment_window.py`
- `tests/test_text_overlap.py`
- `configs/japanese.default.json`

### 実装内容

#### 1. AudioHistoryを責務分割

現在の `AudioHistory.with_preroll()` は、`last_seg_end` によって前セグメントへのプリロール侵入を完全に禁止する。
これを直接壊さず、既存動作用の互換モードと、日本語境界修復用のoverlapモードを分ける。

例:

```python
class SegmentWindowBuilder:
    def build(
        self,
        *,
        history: AudioHistory,
        speech_start: int,
        speech_end: int,
        speech_samples: np.ndarray,
        pre_context_s: float,
        post_context_s: float,
        max_overlap_s: float,
        allow_previous_overlap: bool,
        forced_split: bool,
    ) -> AudioWindow:
        ...
```

#### 2. 設定値をハードコードしない

初期実験範囲:

| パラメータ | 候補 |
|---|---|
| pre-context | 0.6 / 0.8 / 1.0 / 1.2秒 |
| post-context | 0.0 / 0.1 / 0.2 / 0.3秒 |
| max overlap | 0.3 / 0.5 / 0.8 / 1.0秒 |
| merge similarity | 0.75 / 0.80 / 0.85 / 0.90 |

ベースライン評価で最適値を選ぶ。
最初から「1.0秒が必ず最良」と決めない。

#### 3. post-contextの取得

VADがセグメントを返す時点では、min-silence分の後続音声がhistoryに入っている。
`context_end` は `history` の現在末尾と設定上限の小さい方とする。
利用可能な音声を超えてゼロ埋めしない。

#### 4. TextOverlapMerger

優先順位:

1. sherpa-onnx結果に安定したtoken timestampがある場合は時間で揃える。
2. ない場合は日本語文字列のsuffix-prefix fuzzy alignmentを使う。
3. 音声窓が重複していない場合は文字列統合を行わない。

API例:

```python
@dataclass
class MergeResult:
    merged_text: str
    current_delta: str
    matched_previous_suffix: str
    matched_current_prefix: str
    similarity: float
    applied: bool


def merge_overlapping_text(
    previous: str,
    current: str,
    *,
    audio_overlap_s: float,
    min_overlap_chars: int = 2,
    max_overlap_chars: int = 40,
    min_similarity: float = 0.82,
) -> MergeResult:
    ...
```

#### 5. 正規化と元文字位置の対応

比較用には次を正規化する。

- NFKC
- 空白除去
- 句読点除去
- 英字のcasefold

ただし、返却文字列は元の表記を使う。
正規化文字と元文字のindex mapを保持する。

#### 6. 誤削除を避けるルール

- 2文字一致はsimilarity 1.0でも原則慎重に扱う。
- 3文字以下は、音声重複が十分長い場合だけ適用する。
- 「はいはい」「そうそう」のような正当な反復を、音声重複なしで潰さない。
- 前文の全体と同じ文字列が次に来ても、音声重複が短ければ削除しない。
- 数字や英字を含む境界は完全一致を優先する。
- merge失敗時はcurrentをそのまま採用する。

#### 7. 出力互換性

SSEやコンソールには少なくとも次を持たせる。

```json
{
  "text": "重複除去後に新しく確定した文字列",
  "raw_text": "ASRがこの音声窓に返した全文",
  "merged_context_text": "グループとしての統合結果"
}
```

既存クライアントが `text` だけを読む場合に壊れないようにする。

### 単体テスト例

```python
def test_exact_japanese_overlap():
    prev = "明日は東京都多摩市に"
    cur = "東京都多摩市に行きます"
    assert merge(...).merged_text == "明日は東京都多摩市に行きます"


def test_punctuation_difference():
    prev = "今日は、会議です。"
    cur = "会議ですよろしくお願いします"
    ...


def test_no_audio_overlap_never_deduplicates():
    ...


def test_legitimate_repetition_is_preserved():
    prev = "はい"
    cur = "はいもう一度説明します"
    ...


def test_english_product_name_overlap():
    prev = "GitHub Actionsを"
    cur = "GitHub Actionsを使います"
    ...
```

### ベンチマーク

PR 0の評価でパラメータgridを実行する。
各組み合わせについて次を出す。

- CER
- deletion数
- insertion数
- boundary deletion数
- p95 latency
- 平均入力窓長
- Refinerの実行時間

### 受け入れ条件

- 境界欠落件数がベースラインから30%以上減る、またはCERが相対10%以上改善する。
- insertionが大幅に増えない。
- p95高速確定遅延が1.25倍以内。
- 重複のない音声では既存出力と同じ。
- 多言語balanced modeでは既定で旧方式を維持してもよい。

### CodexへのPR 2指示

```text
PR 2だけを実装してください。
AudioHistoryを巨大化させず、音声窓生成と文字列重複除去を別モジュールにしてください。
音声区間に実際の重複がある場合だけ重複除去を許可し、日本語の正当な反復を削らない保守的な実装にしてください。
既存のAudioHistoryテストを維持し、新しいoverlapモードの単体テストを追加してください。
```

---

## PR 3: 構造化結果とQuality Gate

### 目的

低品質区間を検出し、後段の再認識を必要な区間だけに限定できるようにする。

### 変更対象

- 新規 `scripts/japanese_types.py`
- 新規 `scripts/quality_gate.py`
- `scripts/asr_engine.py`
- `scripts/realtime_transcribe.py`
- `scripts/subtitle_server.py`
- `scripts/ws_protocol.py`
- `tests/test_quality_gate.py`

### 実装内容

#### 1. sherpa-onnx結果のフィールド調査

まず小さな調査スクリプトを作り、`stream.result` が現在のバージョンで返す属性を記録する。

```bash
python scripts/inspect_reazon_model.py --inspect-result test.wav
```

確認対象:

- `text`
- `tokens`
- `timestamps`
- `lang`
- その他スコア関連フィールド

存在しない属性へ依存しない。

#### 2. `_decode_full` の段階的移行

既存のtuple返却を一度に壊さず、新しい内部関数を追加する。

```python
def _decode_result(...) -> DecodeResult:
    ...


def _decode_full(...):
    result = _decode_result(...)
    return result.raw_text, result.metadata.get("lang", "")
```

#### 3. risk signal

MVPで扱うsignal:

- `empty_output`
- `very_low_chars_per_second`
- `very_high_chars_per_second`
- `excessive_repetition`
- `unexpected_latin_ratio`
- `boundary_forced_split`
- `short_boundary_overlap`
- `digit_loss`
- `primary_refine_disagreement`
- `secondary_disagreement`
- `suspicious_single_character`
- `unresolved_lexicon_candidate`

しきい値は `configs/japanese.default.json` に置く。

#### 4. risk score

最初はルールベースの重み付き和でよい。
ただし「confidence」とは呼ばない。

```python
score = min(1.0, sum(weight[reason] for reason in reasons))
```

評価セットで、risk scoreが高いほどCERも高くなるかを確認する。

#### 5. telemetry

コンソールの通常表示を過剰に増やさず、`--debug-quality` またはJSONL出力時だけ詳細を出す。

```json
{
  "risk_score": 0.65,
  "risk_reasons": ["boundary_forced_split", "primary_refine_disagreement"],
  "risk_signals": {"chars_per_second": 0.8, "normalized_edit_distance": 0.42}
}
```

### テスト

- 空文字。
- 異常反復。
- 日本語文中の過剰Latin文字。
- 正常な日英混在固有名詞は過剰riskにしない。
- 数字消失。
- しきい値境界。
- 未知signalがあってもクラッシュしない。

### 受け入れ条件

- 高risk群のCERが低risk群より明確に高い。
- 第2段候補となる区間を20%前後に絞れるしきい値を提示する。
- risk情報を無効にしても既存出力が変わらない。
- 未校正値をconfidenceとして外部公開しない。

### CodexへのPR 3指示

```text
PR 3だけを実装してください。
sherpa-onnxから取得できないスコアを捏造しないでください。
まずresult属性を調査できるツールを追加し、存在するフィールドだけをDecodeResultへ保存してください。
品質値はconfidenceではなくrisk_scoreとして実装し、理由を必ず列挙できるようにしてください。
```

---

## PR 4: 日本語固有名詞辞書と決定的正規化

### 目的

単純な `str.replace` を維持しつつ、より安全な読み・形態素境界ベースの日本語辞書を追加する。

### 変更対象

- 新規 `scripts/japanese_lexicon.py`
- 新規 `scripts/japanese_normalizer.py`
- `scripts/asr_engine.py`
- `scripts/realtime_transcribe.py`
- `requirements.txt` は原則変更不要
- `configs/lexicon.example.jsonl`
- `tests/test_japanese_lexicon.py`
- `tests/test_japanese_normalizer.py`

### 実装内容

#### 1. 既存 `--replace` を残す

互換性のため削除しない。
ただしREADMEでは、短い一般語を登録しないよう注意する。

#### 2. 新しい `--lexicon`

```bash
python scripts/realtime_transcribe.py \
  --mode single --lang ja \
  --lexicon configs/my_lexicon.jsonl
```

#### 3. 形態素解析

既存依存の `fugashi` + `unidic-lite` を使用する。
UniDic featureの属性差を吸収する薄いadapterを作る。

取得候補:

- surface
- lemma
- kana / reading
- part-of-speech
- start/end offsets

featureが欠けた場合は、読みベース補正を無効化してalias完全一致だけを使う。

#### 4. 補正順序

1. 完全なalias一致。
2. 長い語を優先した形態素境界一致。
3. `safe=true` のエントリだけ読み近似一致。
4. `safe=false` は候補スコアにのみ利用。

#### 5. 読み近似

- ひらがなへ統一。
- 長音・小書き文字を比較用に正規化するが、過剰正規化しない。
- 編集距離しきい値は語長で変える。
- 4モーラ未満の読み近似置換は原則禁止。
- 一般名詞と衝突する語は `safe=false` を推奨。

#### 6. 補正ログ

デバッグ時にだけ出す。

```json
{
  "before": "リーザンスピーチ",
  "after": "ReazonSpeech",
  "rule": "alias",
  "entry": "ReazonSpeech"
}
```

#### 7. JapaneseNormalizer

最低限:

- Unicode NFKC
- 不要な連続空白
- 全角ASCIIの正規化
- ReazonSpeech由来の装飾括弧除去
- 句読点前後の空白整理
- ASCII数字を保持
- raw textを保持

数字の音声読みから数字への変換は曖昧性が高い。
最初から包括的ITNを作らず、評価例がある規則だけを追加する。

例:

- `バージョン ごーてんろく` → `バージョン5.6` は周辺語があるときだけ。
- `ごじゅう ギガバイト` → `50GB` は単位語があるときだけ。
- 一般文中の単独の「ご」を `5` にしない。

#### 8. 出力

- `raw_text`: ASRの直接出力。
- `display_text`: 辞書、句読点、表示用整形後。
- `normalized_text`: 検索・保存向けITN後。

### テスト

- alias完全一致。
- 読み一致。
- 短い一般語の誤置換防止。
- 部分文字列の誤置換防止。
- 複数辞書語はlongest-first。
- 英字製品名。
- 数字・型番。
- feature不足時のフォールバック。
- raw textが不変。

### 受け入れ条件

- 固有名詞term recallが20ポイント以上改善する。
- 誤挿入率1%以下。
- raw textが常に取得可能。
- `--lexicon` を指定しなければ既存結果を変えない。

### CodexへのPR 4指示

```text
PR 4だけを実装してください。
既存の--replaceは後方互換のため残し、新しい--lexiconを追加してください。
fugashi/unidic-liteは既存依存を使い、短い一般語や部分文字列を誤って置換しない保守的なルールにしてください。
ASRのraw_textを絶対に上書きしないでください。
```

---

## PR 5: ReazonSpeech hotword/tokenizer調査

### 目的

日本語hotwordが実現可能かを、推測ではなくモデル資産とA/Bテストで確認する。

### 重要方針

このPRはまず **調査PR** とする。
符号化方法を実証できない場合、本番機能として有効化しない。

### 変更対象

- 新規 `scripts/inspect_reazon_model.py`
- 新規 `docs/JA_HOTWORDS.md`
- 必要に応じて `scripts/reazon_tokenizer.py`
- 必要に応じて `scripts/asr_engine.py`
- `tests/test_reazon_tokenizer.py`

### 調査項目

#### 1. `tokens.txt`

- トークン数。
- special token。
- UTF-8 byte表現か。
- SentencePiece由来か。
- byte fallbackか。
- 1文字をどのtoken列で表すか。

#### 2. ONNX metadata

encoder/decoder/joinerのmetadataを出力する。

- model type
- vocab size
- tokenizer hints
- version
- sample rate

#### 3. 配布アーカイブ

- `bpe.model`
- `tokenizer.json`
- `vocab.json`
- `merges.txt`

が存在するかを確認する。

#### 4. 符号化候補

次を順番に検証する。

1. 同梱tokenizer資産を使用。
2. 元モデルの公式tokenizerを、ライセンスを確認して取得。
3. tokensだけから一意に再構成可能か確認。
4. 不可能ならhotword decode biasは断念し、辞書／後段再スコアへ移す。

byte-level BPEは通常、語彙だけではmerge rankを再構成できない可能性がある。
曖昧なgreedy longest-matchを本番に入れない。

### A/B評価

最低50発話を用意する。

- 25件: hotwordを実際に含む。
- 25件: 音が近いがhotwordを含まないnegative例。

測定:

- term recall
- false positive rate
- CER
- decode latency
- メモリ

### 実装の受け入れ条件

本番有効化にはすべて必要。

- すべての評価hotwordが未知tokenなしで符号化できる。
- term recallが有意に改善する。
- false positive rate 1%以下。
- 通常CERが悪化しない。
- 起動時に失敗を黙殺しない。

満たさない場合:

- `--hotwords` の既存警告を維持。
- `docs/JA_HOTWORDS.md` に調査結果を記録。
- PR 4のlexiconを推奨経路にする。

### CodexへのPR 5指示

```text
PR 5は調査を先にしてください。
ReazonSpeechのtokens.txtだけからtokenizerを推測して本番実装しないでください。
モデルファイル、ONNX metadata、配布アーカイブを検査するCLIを作り、hotword文字列をtoken IDへ変換できる根拠を示してください。
A/B評価を通過しない限り、機能を既定有効にしないでください。
```

---

## PR 6: 選択的な第2段ASR

### 目的

全音声を重いモデルで処理せず、Quality Gateが高riskと判断した区間だけ高精度候補を生成する。

### 変更対象

- 新規 `scripts/secondary_asr.py`
- 新規 `scripts/candidate_selector.py`
- `scripts/realtime_transcribe.py`
- `scripts/download_models.py`
- `tests/test_candidate_selector.py`
- `docs/JA_EVALUATION.md`
- `THIRD_PARTY_NOTICES.md`

### 設計

#### 1. Protocol

```python
from typing import Protocol


class SecondaryASR(Protocol):
    model_id: str

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> DecodeResult:
        ...
```

#### 2. バックエンド候補

最初から採用モデルを固定しない。
同一評価で比較する。

候補:

- ReazonSpeechの非量子化または混合量子化構成が入手できる場合、その高精度版。
- sherpa-onnxで利用可能なQwen3-ASR 0.6B INT8。
- 日本語Moonshine base/tinyの量子化版。
- Parakeet日本語版。

現在の `sherpa-onnx==1.13.6` が各モデル形式をサポートするかを最初に確認する。
モデル資産が存在しても、ランタイムが対応しているとは限らない。

#### 3. 第2段の発火条件

初期条件:

- `risk_score >= threshold`
- `forced_split`
- primary/refineの正規化編集距離が大きい
- 固有名詞辞書候補が未解決
- 数字が高速認識とRefinerで不一致
- 異常反復

発火しない条件:

- 音声が短すぎる。
- BGM/SFXと判断され、両モデルが空に近い。
- 直近の第2段処理が詰まっている。
- 1セッションの実行率上限を超えた。

#### 4. 非同期実行

高速確定をブロックしない。

- 高速結果を先に出す。
- 第2段はFIFO workerへ送る。
- 改善候補が採用された場合だけ`correction`または`refine`イベントを出す。
- 同一セグメントIDで更新する。
- 古い修正が新しいセグメントより後に誤って適用されないよう、sequence IDを使う。

#### 5. CandidateSelector

異なるモデルの生スコアは直接比較しない。
次の決定的条件を使う。

棄却条件:

- 数字を失う。
- 元候補の70%未満の長さで、音声が長い。
- 異常反復が増える。
- 日本語なのに不自然なLatin比率が増える。
- 辞書語を根拠なく別語へ変える。

加点:

- term coverageが高い。
- repetitionが少ない。
- 文字密度が正常範囲。
- Refiner候補と一致する。
- 数字・型番が維持される。

候補差が小さい場合はprimaryを維持する。

#### 6. 設定例

```json
{
  "secondary": {
    "enabled": false,
    "backend": "qwen3-asr-0.6b-int8",
    "risk_threshold": 0.6,
    "max_invocation_ratio": 0.2,
    "queue_size": 4,
    "timeout_s": 10.0
  }
}
```

既定は `enabled=false` から始める。
評価を通過した後だけ変更する。

### 評価

各候補モデルについて次を比較する。

- 全体CER
- 高risk群CER
- 固有名詞F1
- 数字完全一致率
- BGM
- 日英混在
- RTF
- p95修正到着時間
- メモリ
- 第2段実行率

### 受け入れ条件

- 第2段対象群のCERを相対20%以上改善。
- 全体CERを悪化させない。
- 第2段実行率20%以下。
- 高速確定のp95をほぼ変えない。
- 数字完全一致率を悪化させない。
- 第2段が失敗・timeoutしてもprimary結果を保持する。

### CodexへのPR 6指示

```text
PR 6だけを実装してください。
第2ASRはProtocolで分離し、最初はfeature flagを既定OFFにしてください。
高速確定をブロックせず、FIFO workerとsegment sequence IDで修正順序を保証してください。
異なるモデルのlogitやscoreを直接比較せず、数字保持、反復、長さ、辞書coverageなどの決定的な品質条件で候補を選んでください。
```

---

## PR 7: 日英混在の改善

### 目的

日本語発話の中に含まれる英語製品名、API名、型番を、発話全体を英語へルーティングせずに正しく扱う。

### 方針

日本語専用プロジェクトでは、次の文を「英語発話」と判定しない。

```text
AWS LambdaからOpenAI APIを呼び出します。
GitHub ActionsでDockerイメージをビルドします。
Qwen3-ASRとReazonSpeechを比較します。
```

### MVP実装

1. Lexiconに英字surfaceと複数の日本語readingを持たせる。
2. primaryのカタカナ・ひらがな出力を英字surfaceへ保守的に戻す。
3. 英字surfaceの前後に日本語がある場合、JapaneseNormalizerが空白を整理する。
4. 数字を含む製品名を一体として扱う。
5. 第2ASRが英字表記を返した場合、CandidateSelectorで辞書coverageを加点する。

### 将来候補

音声内の短い区間ごとに日本語ASRと英語ASRを並列実行し、timestampで統合する方式は計算量と複雑性が高い。
MVP後、日英混在評価で辞書方式が不十分な場合にのみ検討する。

### 受け入れ条件

- 指定した英語固有名詞の完全一致率80%以上。
- 一般的な日本語カタカナ語を無関係な英字へ変換しない。
- 発話全体を英語ASRへ送らない。

---

## PR 8: パッケージ整理、名称変更、公開準備

### 目的

精度改善が確認できた後に、独立プロジェクトとして整理する。

### 作業

- プロジェクト名を確定。
- CLIコマンド名を決定。
- Pythonパッケージ化を検討。
- 元プロジェクトのMIT著作権表示を保持。
- 派生元をREADMEに明記。
- `THIRD_PARTY_NOTICES.md` を更新。
- モデルごとのライセンスを確認。
- GitHub ActionsをWindows / macOS / Ubuntuのモデル不要テストで実行。
- モデルを使うベンチマークは手動またはself-hosted runnerに分離。
- 設定スキーマのversionを付ける。
- SSE / WebSocketイベントにschema versionを付ける。

### 名称別の公開方法

#### Hayamimi-JA

```text
Hayamimi-JA is a Japanese-specialized derivative of hayamimi.
```

元プロジェクトとの関係を前面に出す。

#### Kotomimi

```text
Kotomimi is based on and derived from hayamimi by oboroge0.
```

独立名称でも、著作権表示と派生関係を明記する。

### 受け入れ条件

- LICENSEに元の著作権表示が残る。
- 追加コードの著作権方針が明確。
- 全モデルのライセンスと配布可否が記載される。
- READMEのベンチマークにはマシン、データ、条件、サンプル数、制約が記載される。

---

# 10. 日本語評価セット設計

## 10.1 推奨規模

MVPでは最低100発話、できれば300発話を目標にする。
同一話者・同一番組に偏らせない。

| カテゴリ | 最低件数 | 主な確認項目 |
|---|---:|---|
| clean mic | 15 | 基本CER |
| conversation | 20 | フィラー、言い直し、省略 |
| far field | 10 | 遠距離・残響 |
| noise | 10 | 雑音耐性 |
| BGM | 10 | 幻覚・空文字 |
| short utterance | 15 | VAD、短文 |
| proper noun | 20 | 辞書、hotword |
| numbers | 20 | 金額、日付、型番 |
| ja-en mixed | 20 | API、製品名 |
| long speech | 10 | forced split、Refiner |

1音声が複数カテゴリに属してよい。

## 10.2 境界専用ケース

次の位置に意図的な無音を入れた評価を作る。

- 助詞の前後。
- 複合名詞の途中。
- 数字と単位の間。
- 英字製品名の前後。
- 文末直前。
- 12秒forced split付近。

例:

```text
「東京都多摩市 / に行きます」
「OpenAI / APIを使います」
「50 / ギガバイトです」
```

## 10.3 音声ライセンス

- ReazonSpeech等の利用条件をmanifestに記録する。
- 再配布不可の音声はURLや生成手順だけをコミットする。
- 個人録音は同意と用途を記録する。
- 音声をCIへアップロードしない。

---

# 11. 指標の定義

## 11.1 CER

NFKC、句読点・空白除去後の文字編集距離を使用する。
raw CERとnormalized CERを分ける。

- `raw_cer`: ASRそのもの。
- `display_cer`: 句読点・辞書後。
- `normalized_cer`: ITN後。

後処理がASR精度を隠さないよう、raw CERを必ず残す。

## 11.2 固有名詞指標

- term recall
- term precision
- term F1
- exact surface match
- reading-equivalent match
- false positive rate

## 11.3 数字指標

- すべての数字列が保存されたか。
- 単位と組になっているか。
- 桁が正しいか。
- 日付の年月日が正しいか。
- バージョンの小数点が正しいか。

## 11.4 ストリーミング指標

- first partial latency
- final latency
- correction latency
- partial revision rate
- boundary deletion rate
- boundary insertion rate
- forced split recovery rate

## 11.5 Quality Gate指標

- risk thresholdごとのcoverage
- high-risk group CER
- low-risk group CER
- fallback invocation ratio
- risk/AER correlation
- 校正後にconfidenceを作る場合はECEとBrier score

---

# 12. 設定ファイル案

`configs/japanese.default.json`

```json
{
  "schema_version": 1,
  "audio": {
    "sample_rate": 16000,
    "min_silence_s": 0.35,
    "max_speech_s": 12.0,
    "pre_context_s": 1.0,
    "post_context_s": 0.2,
    "max_overlap_s": 0.8
  },
  "primary_asr": {
    "backend": "reazonspeech-zipformer-int8",
    "decoding_method": "modified_beam_search",
    "threads": 4
  },
  "text_merge": {
    "enabled": true,
    "min_overlap_chars": 2,
    "max_overlap_chars": 40,
    "min_similarity": 0.82
  },
  "quality": {
    "enabled": true,
    "risk_threshold": 0.6,
    "weights": {
      "empty_output": 1.0,
      "excessive_repetition": 0.5,
      "boundary_forced_split": 0.2,
      "digit_loss": 0.8,
      "primary_refine_disagreement": 0.4
    }
  },
  "lexicon": {
    "enabled": false,
    "path": ""
  },
  "secondary": {
    "enabled": false,
    "backend": "none",
    "max_invocation_ratio": 0.2,
    "queue_size": 4
  }
}
```

実験で確定していない値にはコメントを付けられないJSONの制約があるため、READMEまたはschema文書で「暫定値」と明記する。
CLI引数が設定ファイルを上書きする。

---

# 13. ロギングとイベントスキーマ

## 13.1 segment ID

すべてのpartial、final、refine、correctionに単調増加のsegment IDを付ける。

```json
{
  "schema_version": 1,
  "type": "final",
  "segment_id": 42,
  "text": "多摩センターへ行きます。",
  "raw_text": "多摩センターへ行きます",
  "model_id": "reazonspeech-zipformer-int8",
  "risk_score": 0.2
}
```

修正イベント:

```json
{
  "schema_version": 1,
  "type": "correction",
  "segment_id": 42,
  "revision": 2,
  "text": "多摩センターへ行きます。",
  "reason": "secondary_asr"
}
```

## 13.2 順序保証

- 同一segmentのrevisionは増加のみ。
- 古いrevisionを配信しない。
- RefinerとSecondary workerが競合しても、CandidateSelectorが最新revisionを確認する。
- セッション再開始時にsession IDを更新する。

## 13.3 個人情報

- 音声そのものは既定で保存しない。
- debug audio dumpは明示フラグがある場合だけ。
- debug出力先を`.gitignore`対象にする。

---

# 14. テスト戦略

## 14.1 モデル不要の単体テスト

CIで常に実行する。

```bash
python -m pytest tests -q
```

対象:

- 音声窓インデックス。
- ローリングバッファ境界。
- テキスト重複統合。
- 辞書parseと補正。
- 正規化。
- risk計算。
- 候補選択。
- CLI設定。
- イベントrevision順序。

## 14.2 モデルありの統合テスト

ローカルまたはself-hosted runnerで実行する。

```bash
python scripts/download_models.py --japanese-only
python scripts/eval_ja_streaming.py \
  --manifest testdata/eval_ja/manifest.jsonl \
  --output artifacts/ja_eval/current
```

## 14.3 回帰ケース

失敗音声ごとに、音声をコミットできない場合でもmetadataを追加する。

```json
{
  "issue": "boundary-loss-001",
  "description": "多摩市の『た』がVADで欠落",
  "expected_contains": "多摩市",
  "category": "boundary"
}
```

## 14.4 プロパティテスト相当の確認

追加依存なしでランダム文字列を生成し、次を確認する。

- 音声重複0ならmergerはcurrentを削らない。
- merge後の文字列はpreviousまたはcurrentの数字列を勝手に消さない。
- normalizerはidempotentである。
- raw_textは常に不変。

---

# 15. 実装時の禁止事項

Codexは次を行わないこと。

1. 評価前にReazonSpeechを全面的に別モデルへ置換する。
2. `str.replace` を削除して後方互換を壊す。
3. モデルが返さないscoreを推測で作る。
4. byte-level BPEのmerge情報なしに、独自greedy tokenizerを本番採用する。
5. 数字をLLMへ自由変換させる。
6. 高速確定を第2モデル待ちでブロックする。
7. モデルファイルをGitへ追加する。
8. 実音声の個人情報をログへ常時保存する。
9. unrelatedなコード整形や大規模リネームを同じPRへ混ぜる。
10. ベンチマーク条件を書かずに「精度向上」とREADMEへ記載する。
11. 既存のbalanced/fastモードを、日本語版完成前に削除する。
12. 単体テストをモデル実体へ依存させる。

---

# 16. リスクと対策

| リスク | 影響 | 対策 |
|---|---|---|
| 音声窓の重複で文字が二重になる | insertion増加 | audio overlap metadata必須、保守的merger、raw保持 |
| fuzzy mergeが正当な反復を消す | 意味変化 | 音声重複なしでは適用禁止、短一致の強い制限 |
| 読み辞書が一般語を誤補正 | 固有名詞の幻覚 | safe属性、最小読み長、形態素境界、negative test |
| hotword tokenizerが再構成できない | 機能未達 | 調査PRとして分離し、辞書／候補選択へフォールバック |
| 第2モデルで遅延・メモリ増加 | UX悪化 | 非同期、risk対象限定、呼出率上限、LRU/明示unload |
| 異なるモデル間で候補比較できない | 誤選択 | raw scoreを比較せず決定的品質ルールを使う |
| 小規模評価へ過適合 | 実環境悪化 | カテゴリ別holdout、話者分離、negative例 |
| 句読点モデルが大きい | 起動・RSS増加 | optional、遅延ロード、句読点なしprofile |
| macOS/Windows差 | 実行失敗 | モデル不要CI matrix、パス処理とspawn動作をテスト |
| upstream変更追従が困難 | 保守コスト | 初期は小さな追加モジュール中心、既存API互換 |

---

# 17. Definition of Done

MVP完了には、次のすべてが必要。

- [ ] PR 0のベースラインが保存されている。
- [ ] 日本語固定時にLIDと他言語モデルをロードしない。
- [ ] VAD境界コンテキストがfeature flag付きで実装されている。
- [ ] text overlap mergerに十分な単体テストがある。
- [ ] raw/display/normalized textを分離している。
- [ ] risk scoreと理由を出せる。
- [ ] 読み・形態素境界ベース辞書が実装されている。
- [ ] hotwordの可否が実証結果付きで文書化されている。
- [ ] 第2ASRがProtocolで分離され、既定OFFである。
- [ ] CandidateSelectorが数字を保護する。
- [ ] 日本語ストリーミングCERが受け入れ目標を満たす。
- [ ] p95高速確定遅延が許容範囲内。
- [ ] term recallとfalse positive rateが目標を満たす。
- [ ] Windows / macOS / Ubuntuでモデル不要テストが通る。
- [ ] LICENSEとTHIRD_PARTY_NOTICESが正しい。
- [ ] READMEに評価条件と限界を記載している。

---

# 18. Codexに最初に渡すプロンプト

以下をそのままCodexへ渡す。

```text
あなたは oboroge0/hayamimi のフォークを編集します。
目的は、CPU・ローカル動作を維持したまま、日本語のリアルタイムASR精度を改善することです。

最初に次を読んでください。
- japanese_asr_codex_development_plan.md
- README.ja.md
- scripts/asr_engine.py
- scripts/realtime_transcribe.py
- scripts/download_models.py
- scripts/eval_accuracy.py
- tests/test_units.py
- docs/BENCHMARKS.md
- docs/EVAL_REAL.md
- docs/LID.md
- docs/PUNCT_JA.md

今回実装するのは計画書の「PR 0: ベースライン固定と評価基盤」だけです。
認識ロジック、VAD設定、モデル選択、既存CLIの既定動作は変更しないでください。

作業手順:
1. 現在のテストを実行し、結果を記録する。
2. 日本語のoffline / VAD fast / VAD refineを同じmanifestから評価できる設計を提案する。
3. scripts/eval_ja_streaming.pyを実装する。
4. 指標計算はモデル不要でテストできるよう分離する。
5. JSON、JSONL、Markdownレポートを生成する。
6. モデルがない環境では統合評価だけをskipする。
7. pytestを実行する。
8. 変更ファイル、テスト結果、未実行項目、次PRへの注意点を報告する。

禁止:
- 全PRを一度に実装しない。
- モデルをGitへ追加しない。
- unrelatedなリファクタをしない。
- ベンチマーク未実行で精度向上を主張しない。
```

---

# 19. PR完了後にCodexへ渡す共通レビュー指示

```text
今回の変更を自己レビューしてください。

確認項目:
- 計画書の当該PR以外へスコープが広がっていないか。
- 既存CLIとイベント形式を壊していないか。
- モデル不要テストが十分か。
- raw_textを失う経路がないか。
- 数字を壊す可能性がないか。
- Windowsのパス、macOS/Linux、thread shutdownで問題がないか。
- バックグラウンドworkerの出力順序が保証されているか。
- モデルがない場合に明確にdegradeするか。
- READMEやdocsの数値に実測条件があるか。

問題があれば修正し、最後に以下を報告してください。
1. 変更概要
2. 変更ファイル一覧
3. 実行したテストと結果
4. 実行できなかったテスト
5. ベンチマーク前後比較
6. 残るリスク
7. 次PRで行うべきこと
```

---

# 20. 推奨開発順序の要約

```text
PR 0  評価基盤
  ↓
PR 1  真の日本語専用プロファイル
  ↓
PR 2  VAD境界コンテキスト + 重複統合
  ↓
PR 3  構造化結果 + Quality Gate
  ↓
PR 4  読み・形態素ベース辞書 + 正規化
  ↓
PR 5  hotword/tokenizer調査
  ↓
PR 6  選択的第2ASR
  ↓
PR 7  日英混在改善
  ↓
PR 8  名称・パッケージ・公開準備
```

最初に期待できる大きな改善は、モデル交換ではなく **PR 1〜PR 4** にある。
特に、VAD経路で失われる音声文脈の回復、重複の安全な統合、固有名詞の保守的補正を優先する。
第2モデルは、これらを実装しても残る高risk区間に限定して使用する。

---

# 21. 参照する上流ファイル

この計画は、次の上流ファイルを基に作成した。
Codexは作業開始時に最新内容との差分を確認すること。

- `README.ja.md`
- `LICENSE`
- `THIRD_PARTY_NOTICES.md`
- `requirements.txt`
- `scripts/asr_engine.py`
- `scripts/realtime_transcribe.py`
- `scripts/download_models.py`
- `scripts/eval_accuracy.py`
- `scripts/eval_engine.py`
- `scripts/punct_ja.py`
- `tests/test_units.py`
- `docs/BENCHMARKS.md`
- `docs/EVAL_REAL.md`
- `docs/LID.md`
- `docs/PUNCT_JA.md`

