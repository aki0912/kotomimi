# 日本語ASR評価データ 品質確認報告

作成日: 2026-09-01

## 1. 概要

日本語ASRのCER（Character Error Rate）評価に使用、または使用候補として確認したデータについて、データソース、機械QC、人手監査、および評価時に確認された問題を整理した。

今回確認した中で、品質上の問題が最も明確だったデータソースは Common Voice Japanese 26.0 である。Google FLEURSのclean viewは重大な問題を除外できているが、同一文章を異なる話者が読む重複データが残る。ReazonSpeech由来の放送音声は、字幕参照と音声区間のずれ、BGM、複数話者、ジングルなどに注意が必要である。

> **重要:** 機械QCのフラグ数、人手監査の品質ラベル、ASRの認識エラーは異なる指標である。たとえばASRの空出力は、直ちに元音声の品質不良を意味しない。また、1件に複数の機械QCフラグが付くため、フラグ数の合計はデータ件数と一致しない。

## 2. データソース別概要

| データソース | 使用・確認件数 | 品質上の位置付け | 主な問題 |
|---|---:|---|---|
| Common Voice Japanese 26.0 test | 全9,020件、CER評価1,000件、人手監査200件 | experimental、正式ゲート不採用 | 音声不良、参照不一致、別言語、長い無音 |
| Google FLEURS `ja_jp` test | 全650件、公式CER評価300件、人手監査100件 | 元のofficial viewはexperimental | 音声不良、無音、発話率判定、重複文 |
| FLEURS clean approved | CER評価・人手監査204件 | approved、補助回帰ゲート | 重大問題なし。重複31件、軽微な参照問題1件 |
| ReazonSpeech test由来放送音声 | CER評価15件 | 小規模な参考評価 | 字幕と音声区間のずれ、BGM、複数話者、ジングル |

## 3. Common Voice Japanese 26.0

### 3.1 データソース

- 名称: Common Voice Scripted Speech 26.0 - Japanese
- バージョン: 26.0
- release: `cv-corpus-26.0-2026-06-12`
- locale: `ja`
- split: `test`
- 全件数: 9,020件
- ライセンス: CC0-1.0
- データ提供ページ: <https://mozilladatacollective.com/datasets/cmqim4lxy00tunr07cjkcupeg>

### 3.2 人手監査

9,020件から監査用に選んだ200件を全件確認した。

| 判定 | 件数 | 割合 |
|---|---:|---:|
| 正常 (`ok`) | 148 | 74.0% |
| 音声不良 (`bad_audio`) | 35 | 17.5% |
| 重大な書き起こし不一致 (`major_transcript_mismatch`) | 6 | 3.0% |
| 軽微な書き起こし問題 (`minor_transcript_issue`) | 8 | 4.0% |
| 別言語 (`wrong_language`) | 2 | 1.0% |
| 音声切れ (`truncated_audio`) | 1 | 0.5% |

非正常判定は52/200件、26.0%だった。監査基準上の重大問題率は21.5%で、許容上限5.0%を超えたため、正式な回帰ゲートには採用していない。音声切れ率は0.5%で、音声切れ単独の許容上限2.0%以内だった。

監査時の付加属性は次のとおりだった。

| 属性 | 件数 | 割合 |
|---|---:|---:|
| clean noise | 175 | 87.5% |
| mild noise | 14 | 7.0% |
| heavy noise | 11 | 5.5% |
| read speech | 200 | 100.0% |

`bad_audio`の詳細な原因は監査コメントへ構造化していないため、35件をノイズ、発音、録音破損などへさらに正確に分類することはできない。

### 3.3 機械QC

9,020件のうち、5,639件（62.5%）がclean view、3,381件（37.5%）がstress viewに分類された。主なフラグは次のとおりである。

| QCフラグ | 件数 | 全9,020件に対する割合 |
|---|---:|---:|
| 末尾無音が長い (`long_trailing_silence`) | 2,604 | 28.9% |
| 冒頭無音が長い (`long_leading_silence`) | 1,621 | 18.0% |
| 発話区間が少ない (`low_speech_fraction`) | 492 | 5.5% |
| 音量が非常に小さい (`very_quiet`) | 222 | 2.5% |
| Latin文字混在 (`latin_mixed`) | 59 | 0.7% |
| 参照が非常に短い (`very_short_text`) | 28 | 0.3% |
| 文字反復 (`repeated_chars`) | 15 | 0.2% |
| 日本語文字率が低い (`low_japanese_ratio`) | 3 | 0.03% |
| 参照が非常に長い (`very_long_text`) | 3 | 0.03% |
| 発話率が高すぎる (`high_speech_fraction`) | 2 | 0.02% |
| 短すぎる音声 (`too_short`) | 1 | 0.01% |
| clipping疑い (`possible_clipping`) | 1 | 0.01% |

QCフラグは重複する。stress viewの3,381件すべてが再生不能または参照不正という意味ではない。

### 3.4 CER評価

official viewから選択した1,000件の評価結果は次のとおりだった。

| 指標 | 結果 |
|---|---:|
| 正規化CER | 24.15% |
| raw CER | 28.97% |
| 置換 | 1,857 |
| 削除 | 2,739 |
| 挿入 | 418 |

このofficial viewはQC除外前のデータを保持しており、監査状態もexperimentalである。このため、24.15%をASRモデルだけの性能として解釈したり、正式なリリースゲートとして使用したりしない。

## 4. Google FLEURS Japanese

### 4.1 データソース

- 名称: Google FLEURS Japanese
- Hugging Face dataset: `google/fleurs`
- config: `ja_jp`
- split: `test`
- 固定revision: `70bb2e84b976b7e960aa89f1c648e09c59f894dd`
- 全件数: 650件
- ライセンス: CC-BY-4.0
- データ提供ページ: <https://huggingface.co/datasets/google/fleurs>

### 4.2 official viewの人手監査

650件から監査用に選んだ100件を全件確認した。

| 判定 | 件数 | 割合 |
|---|---:|---:|
| 正常 (`ok`) | 86 | 86.0% |
| 音声不良 (`bad_audio`) | 10 | 10.0% |
| 重複 (`duplicate`) | 2 | 2.0% |
| 軽微な書き起こし問題 (`minor_transcript_issue`) | 2 | 2.0% |

重大問題率は10.0%で、許容上限5.0%を超えた。このため、元のofficial viewは正式な回帰ゲートとして承認していない。

監査用100件のノイズ属性はclean 60件、mild 40件で、すべてread speechだった。

### 4.3 機械QC

650件のうち、204件（31.4%）がclean view、446件（68.6%）がstress viewに分類された。

| QCフラグ | 件数 | 全650件に対する割合 |
|---|---:|---:|
| 発話率が高すぎる (`high_speech_fraction`) | 270 | 41.5% |
| 冒頭無音が長い (`long_leading_silence`) | 174 | 26.8% |
| 末尾無音が長い (`long_trailing_silence`) | 79 | 12.2% |
| 発話率が低い (`low_speech_fraction`) | 79 | 12.2% |
| 音量が非常に小さい (`very_quiet`) | 79 | 12.2% |
| Latin文字混在 (`latin_mixed`) | 66 | 10.2% |
| clipping疑い (`possible_clipping`) | 2 | 0.3% |

同一参照文を持つ音声は552件、223グループあった。これは異なる話者が同じ文章を読む正常なFLEURSデータも含む。音声と参照の組が完全に同一の重複、音声ファイルの重複、source IDの重複は確認されていない。

発話率が高いというだけで音声品質が悪いとは限らない。したがって、stress viewの68.6%を「不良データ率」として報告してはならない。

### 4.4 official viewのCER評価

official viewから選択した300件では、正規化CER 8.96%、raw CER 14.78%、置換742、削除443、挿入163だった。ただし、この評価時点では人手監査が未承認またはexperimentalだったため、参考値として扱う。

## 5. FLEURS clean approved 204件

機械QCを通過した204件について、同一のclean viewを全件人手確認した。

| 判定 | 件数 | 割合 |
|---|---:|---:|
| 正常 (`ok`) | 172 | 84.3% |
| 重複 (`duplicate`) | 31 | 15.2% |
| 軽微な書き起こし問題 (`minor_transcript_issue`) | 1 | 0.5% |
| 音声不良 | 0 | 0.0% |
| 重大な書き起こし不一致 | 0 | 0.0% |
| 別言語 | 0 | 0.0% |
| 音声切れ | 0 | 0.0% |

重大問題率、音声切れ率はいずれも0%で、補助回帰ゲートとして承認されている。204件はすべてnoise属性がclean、speech styleがreadだった。

重複31件は自動除外していない。異なる話者による同一文章の読み上げはASR評価として有効だが、特定の文章がCERへ複数回寄与し、文章多様性が低下する可能性がある。

### 5.1 CER評価

| 評価経路 | 件数 | CER | 置換 | 削除 | 挿入 |
|---|---:|---:|---:|---:|---:|
| オフライン評価 | 204 | 9.43% | 570 | 318 | 107 |
| ストリーミング評価、PR 2 overlap有効 | 204 | 8.77% | 597 | 197 | 133 |

評価経路と出力処理が異なるため、9.43%と8.77%の差をデータ品質の改善量として扱わない。現行ストリーミング経路の品質管理済みCERとしては8.77%を使用する。

## 6. ReazonSpeech由来の放送音声15件

### 6.1 データソース

- 上流データ: ReazonSpeech test split
- 取得元: Hugging Face上の `japanese-asr/ja_asr.reazonspeech_test` ミラー
- 音声ドメイン: 日本のテレビ放送
- 評価件数: 15件
- 抽出条件: 主に3～9秒、必要に応じて最大15秒
- 前処理: 16 kHz、mono、16-bit PCM WAVへ変換
- 上流ページ: <https://huggingface.co/datasets/reazon-research/reazonspeech>

ニュース、スポーツ、ドラマ、CM・ジングルなどを含み、FLEURSやCommon Voiceの読み上げ音声とはドメインが異なる。

### 6.2 CERと認識結果上の兆候

| 指標 | 結果 |
|---|---:|
| CER | 13.40% |
| 置換 | 10 |
| 削除 | 16 |
| 挿入 | 13 |
| 空出力 | 1/15件（6.67%） |
| alignment上の語頭欠落 | 2件 |
| alignment上の語末欠落 | 2件 |
| Quality Gate high-risk | 11/15件（73.33%） |
| high-risk群CER | 16.97% |
| low-risk群CER | 2.74% |

空出力、境界欠落、high-risk判定はASR出力側の兆候であり、それ自体を元データの不良判定として数えてはならない。

### 6.3 確認された注意例

- `ja_broadcast_002`: 「ピカピカブ」というジングル音声で、通常の会話・読み上げ発話とは性質が異なる。ストリーミング評価では空出力だった。
- `ja_broadcast_006`: 参照にない「ずいぶんありましたけどね」が認識された。参照が音声全体を覆っていない可能性が高く、挿入誤りとしてCERへ加算されている。
- 過去のクリップ全体評価では、`ja_broadcast_004`、`ja_broadcast_011`、`ja_broadcast_013`についても、複数モデルが参照外の前後発話を同様に認識した。字幕参照と切り出し区間のずれが疑われる。

参照外発話は少なくとも4/15件で疑われるが、これは正式な人手監査ラベルではなく、音声内容と複数モデルの共通出力からの推定である。

ReazonSpeechの参照は放送字幕形式であり、句読点や表記規則だけでなく、実際に聞こえる発話全体と参照範囲が一致しない可能性がある。このため、15件のCERはストリーミング処理の小規模な参考比較には使用できるが、統計的に安定した一般精度や商用利用可能な正式評価セットの値として扱わない。

### 6.4 利用条件上の注意

本プロジェクトの商用評価データ管理では、ReazonSpeech datasetを利用不可リストに登録している。理由は、利用が日本国著作権法30条の4の対象目的に限定されるためである。商用利用可能な評価データとして結果を外部報告する場合、FLEURSおよびCommon Voiceの結果と分離する。

## 7. 推奨する報告文

> Common Voice Japanese 26.0では、人手確認200件中52件（26.0%）に何らかの問題があり、音声不良35件、重大な書き起こし不一致6件、別言語2件、音声切れ1件が確認された。監査基準上の重大問題率は21.5%であり、正式な精度ゲートから除外した。
>
> Google FLEURS Japaneseでは、機械QCと人手確認を通過したclean view 204件をストリーミングCER評価に使用した。このセットでは重大な音声・書き起こし問題、別言語、音声切れは0件だった。一方、異なる話者による同一文章を含む重複判定が31件、軽微な書き起こし問題が1件あった。現行ストリーミング経路でのCERは8.77%だった。
>
> ReazonSpeech由来の放送音声15件は参考評価として使用したが、字幕参照と実際の音声区間が一致しない可能性、BGM、複数話者、ジングル、前後発話の混入がある。さらに利用条件上、商用評価用の正式なデータセットには含めていない。

## 8. 根拠となるプロジェクト内成果物

- Common Voice人手監査: `benchmarks/ja_eval/artifacts/audit_reports/common_voice_ja_26-20260829-200-0497e82fbb3d/audit-report.json`
- Common Voice機械QC: `benchmarks/ja_eval/artifacts/qc/common_voice_ja_26/0497e82fbb3d4a82/qc.json`
- FLEURS official人手監査: `benchmarks/ja_eval/artifacts/audit_reports/fleurs_ja-20260829-100-2ea731373775/audit-report.json`
- FLEURS機械QC: `benchmarks/ja_eval/artifacts/qc/fleurs_ja/2ea73137377569b0/qc.json`
- FLEURS clean人手監査: `benchmarks/ja_eval/artifacts/audit_reports/fleurs_ja-clean-20260829-204-2ea731373775/audit-report.json`
- Common Voice/FLEURS official CER: `benchmarks/ja_eval/artifacts/runs/20260829T233330Z-hayamimi-ja-6261f9cb/report.json`
- FLEURS clean approved CER: `benchmarks/ja_eval/artifacts/runs/20260830T004258Z-hayamimi-ja-20aabaee/report.json`
- FLEURS streaming CER: `artifacts/ja_eval/pr3-quality-fleurs-final2/report.md`
- ReazonSpeech streaming CER: `artifacts/ja_eval/pr3-quality-broadcast-final3/report.md`
- Quality Gate条件: `docs/QUALITY_GATE.md`
- 実音声データの由来: `docs/EVAL_REAL.md`

## 9. 解釈上の制約

- Common Voiceの200件監査とCER評価1,000件は、全9,020件に対する異なる抽出評価である。監査率をCER評価1,000件の実不良率として断定しない。
- FLEURS officialの100件監査と300件CER評価も異なる抽出である。
- FLEURS clean 204件については、CER評価に使った同一viewを全件監査している。
- ReazonSpeech 15件には正式な人手監査ラベルがない。参照ずれ件数は推定を含む。
- CERの置換・削除・挿入はASR出力と参照の差であり、データ品質エラーの件数ではない。
- official、clean、stress、およびストリーミングの数値は、対象viewや評価経路が異なる場合がある。条件を併記せずに直接比較しない。
