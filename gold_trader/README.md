# AI GOLD Trader (XM / MT5)

Pythonで動くXAUUSD（ゴールド）5分足の自動売買ボット。
合成データでのバックテストと、XMデモ口座へのライブ接続(MT5経由)に対応。

## ⚠️ 重要な注意

- **「勝率95%」は現実的ではありません。** このボットは現実的な勝率55〜60%、リスクリワード1:1.66、期待値プラスを狙う設計です。
- **必ずデモ口座で十分に検証してから**本番運用を検討してください。
- 過去のバックテスト結果は将来のパフォーマンスを保証しません。

## 戦略概要

| 要素 | 内容 |
|---|---|
| 銘柄 | XAUUSD |
| 時間足 | M5 (5分) |
| エントリー | EMA9/21クロス + EMA50トレンドフィルタ |
| 補助フィルタ | RSI(14)極端値回避, ADX(14) > 20 |
| 取引時間 | UTC 7-16時 (ロンドン/NY) |
| SL | 1.5 × ATR |
| TP | 2.5 × ATR (RR ≈ 1:1.66) |
| ポジションサイズ | 残高の1%リスク |

## ファイル構成

```
gold_trader/
├── config.py          # 全パラメータ
├── indicators.py      # EMA / RSI / ATR / ADX
├── strategy.py        # シグナル生成 + サイジング
├── data_loader.py     # 合成データ生成 + MT5データ取得
├── backtest.py        # バックテスト本体
├── live_trader.py     # XM デモへのライブ接続
├── requirements.txt
├── .env.example       # MT5 ログイン情報テンプレ
└── logs/              # 結果出力先
```

## セットアップ

```bash
cd gold_trader
pip install -r requirements.txt
```

## 1. バックテスト (合成データ・MT5不要)

合成のXAUUSD 5分足データを生成して戦略を検証します。MT5なしで動きます。

```bash
python backtest.py --days 120 --seed 42
```

オプション:
- `--days N` 生成する日数 (デフォルト120日)
- `--seed N` 乱数シード (再現性確保)
- `--verbose` 各トレードを表示

出力: `logs/trades.csv`, `logs/equity.csv`, `logs/metrics.json`

### 期待される指標
合成データなので絶対値は参考程度ですが、現実的なシステムなら:
- 勝率: 45〜60%
- プロフィットファクタ: 1.2〜1.8
- 最大DD: 5〜20%

## 2. XMデモ口座でのライブトレード (Windowsのみ)

### 前提
1. **Windows PC** (MetaTrader5 PythonパッケージはWindowsのみ)
2. **XMデモ口座** ([XM公式サイト](https://www.xmtrading.com)で開設)
3. **MT5デスクトップアプリ** をインストール、デモ口座でログイン

### 設定
```bash
cp .env.example .env
# .env を開いて MT5_LOGIN / MT5_PASSWORD / MT5_SERVER を記入
```

### 実行
```bash
# まずドライラン (注文を出さずシグナルだけ確認)
python live_trader.py --dry-run

# 本番ループ (デモ口座に注文を送る)
python live_trader.py
```

ログには各5分足クローズ毎のシグナル判断と、エントリー時の注文結果が出ます。

## 3. 実データでバックテスト

`data_loader.load_mt5_history()` を使えば、MT5から実データを取得して `run_backtest()` に渡せます:

```python
from data_loader import load_mt5_history
from backtest import run_backtest, metrics

df = load_mt5_history("XAUUSD", 5, bars=20_000)
trades, equity = run_backtest(df)
print(metrics(trades, equity))
```

## チューニングの方向性

`config.py` のパラメータを調整:
- ボラの低い相場: `adx_threshold` を下げる、`sl_atr_mult` を小さく
- 偽シグナルが多い: `ema_trend` を100や200にして強いトレンドのみ取る
- 取引が少なすぎる: 取引時間を広げる、`adx_threshold` を15に
- 取引が多すぎる/負けが多い: `adx_threshold` を25に上げる

## 次のステップ案

1. **ウォークフォワード最適化** — 期間を分けてパラメータ最適化 → アウトオブサンプル検証
2. **機械学習の追加** — XGBoost等で勝率の高いシグナルだけフィルタ
3. **マルチタイムフレーム** — H1のトレンドと整合するM5シグナルだけ取る
4. **ニュース回避** — 重要指標時間にエントリーしないフィルタ

## リスク開示

外国為替・差金決済取引はハイリスクです。元本の全部または一部を失う可能性があります。
このコードは教育目的であり、投資助言ではありません。実資金での運用は自己責任でお願いします。
