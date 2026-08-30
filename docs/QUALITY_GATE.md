# 日本語ASR Quality Gate

Quality Gateは、認識結果が誤っている可能性を説明可能な`risk_score`として表す。
正解確率やconfidenceではなく、後段の再認識候補を絞るためのルールベース指標である。
通常のCLI・SSEイベントは変更せず、`--debug-quality`指定時だけtelemetryを出す。

## ReazonSpeech結果属性

2026-08-30、macOS arm64、Python 3.11.9、sherpa-onnx 1.13.6、
`sherpa-onnx-zipformer-ja-en-reazonspeech-2025-01-17`で確認した
`OfflineRecognitionResult`の公開属性は次の通りだった。

- `text`
- `tokens`
- `timestamps`
- `ys_log_probs`
- `lang`
- `durations`
- `emotion`
- `event`
- `segment_durations`
- `segment_texts`
- `segment_timestamps`
- `words`

このモデルでは`tokens`、`timestamps`、`ys_log_probs`に値があり、`lang`とその他の
segment系属性は空だった。実環境では次のコマンドで再調査できる。

```bash
python scripts/inspect_reazon_model.py --inspect-result testdata/eval_real/ja_01.wav
```

`ys_log_probs`はモデル固有のtoken log probabilityとしてそのまま保存する。
校正済みの正解確率ではないためconfidenceへ変換しない。属性が存在しないモデルでは
空tupleとして扱い、`low_token_log_probability`理由を付けずにdegradeする。

## risk signal

`scripts/quality_gate.py`はモデルをロードせず、次を判定する。

- 空出力、文字密度の過小・過大、異常反復
- 日本語出力として不自然なLatin文字率
- 強制分割、短すぎる境界overlap
- raw/display間の数字消失
- primary/refineおよびsecondary候補との不一致
- 不自然な1文字出力、未解決辞書候補
- ReazonSpeechの低い平均token log probability

理由ごとの重みと閾値は`configs/japanese.default.json`に置く。未知signalはtelemetryへ
保存できるが、既知の重み一覧にない理由を暗黙に加点しない。

## telemetry

```json
{
  "quality": {
    "risk_score": 0.35,
    "risk_reasons": ["low_token_log_probability"],
    "risk_signals": {
      "mean_token_log_probability": -0.27,
      "chars_per_second": 4.2,
      "high_risk": true
    }
  }
}
```

通常実行では`quality`フィールドを追加しない。評価では次のようにJSON、JSONL、Markdownへ
risk情報を記録する。

```bash
python scripts/eval_ja_streaming.py \
  --manifest testdata/eval_ja/manifest.jsonl \
  --modes stream_single_ja --ja-overlap --quality-gate
```

## 校正結果

監査済みFLEURS日本語clean 204件、`stream_single_ja`、PR 2 overlap有効、4 threads、
`min_silence=0.35`、`max_speech=12.0`で校正した。

| group | 件数 | 比率 | CER |
|---|---:|---:|---:|
| high risk | 43 | 21.08% | 14.54% |
| low risk | 161 | 78.92% | 7.14% |

全体CERは8.77%だった。高risk群は低risk群の約2.04倍で、再認識候補を約20%へ
絞る目的を満たした。一方、ReazonSpeech放送音声15件ではBGM・自然会話により11件が
high riskとなった。該当群CER 16.97%、low risk群2.74%で順位付けは機能したが、選別率は
73.33%と高い。現在の閾値は読み上げcleanセットで校正した値であり、全ドメイン共通の
確率ではない。次段の再認識を既定有効にする前に、自然会話を含む大きな検証セットで
ドメイン別閾値またはrolling calibrationを検討する。
