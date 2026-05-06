# XMデモ口座セットアップ手順

このドキュメントは、Pythonボット (`live_trader.py`) を XM のデモ口座に繋ぐまでの完全手順です。

> **前提**: Windows PC が必要です (`MetaTrader5` Pythonパッケージは Windows 専用)。
> Mac/Linux の方は仮想環境 (Parallels, VMware, Wine等) または Windows VPS を使ってください。
> 検証だけなら `backtest.py` で十分なので、無理にライブにしなくてOKです。

---

## ステップ 1: XMデモ口座を開設

1. https://www.xmtrading.com/jp/ にアクセス
2. 「**デモ口座開設**」をクリック
3. 必須項目を入力:
   - 取引プラットフォーム: **MT5**
   - 口座タイプ: **スタンダード** (または Zero)
   - レバレッジ: 任意 (デモなので1:500等でOK)
   - 投資額: USD 10,000 (任意)
4. メールでログイン情報が届く:
   - **MT5 ID** (8桁前後の数字) ← `MT5_LOGIN`
   - **パスワード** ← `MT5_PASSWORD`
   - **サーバ名** (例: `XMTrading-Demo 3`) ← `MT5_SERVER`

これら3つは後で `.env` に記入します。

---

## ステップ 2: MT5 デスクトップアプリのインストール

1. https://www.xmtrading.com/jp/platforms/mt5 から **XMTrading MT5 (Windows)** をダウンロード
2. インストーラを実行
3. 起動 → 「ファイル」→「取引口座にログイン」
4. ステップ1で受け取った ID / パスワード / サーバを入力してログイン
5. 画面右下のステータスが緑色（接続済み）になるか確認
6. 上部メニューの「**アルゴリズム取引**」ボタンをクリックして緑色（有効）に

> XMには複数のMT5バージョンがあります。**XMTrading 公式版** をインストールしてください
> (汎用 MetaQuotes版だとXMサーバへ接続できない場合あり)。

---

## ステップ 3: Python 環境の準備 (Windows側)

PowerShell または コマンドプロンプトで:

```powershell
# Python 3.10〜3.12 推奨 (3.13 はまだ MetaTrader5 が未対応のことあり)
python --version

# プロジェクトを取得
git clone <このリポジトリのURL>
cd shopfy\gold_trader

# 仮想環境
python -m venv .venv
.venv\Scripts\activate

# 依存パッケージ
pip install -r requirements.txt
pip install MetaTrader5
```

> もし `pip install MetaTrader5` が失敗する場合は Python 3.11 をインストールし直してください。

---

## ステップ 4: `.env` の作成

```powershell
copy .env.example .env
notepad .env
```

`.env` の中身:

```ini
MT5_LOGIN=12345678
MT5_PASSWORD=xxxxxxxx
MT5_SERVER=XMTrading-Demo 3
# 必要なら ↓ の行を有効化 (複数MT5があるとき)
# MT5_PATH=C:\Program Files\XMTrading MT5\terminal64.exe
```

> サーバ名はXMからのメールに記載されている文字列を**完全一致**で入れてください。
> 「XMTrading-Demo 3」の場合は `XMTrading-Demo 3` (スペース含む)。

---

## ステップ 5: 接続診断

注文を一切送らずに、設定が正しいかチェックします:

```powershell
python check_connection.py
```

成功すると以下のような出力:

```
[1] MetaTrader5 パッケージ
  [OK]  import MetaTrader5  — version=5.0.45

[2] 環境変数 (.env)
  [OK]  MT5_LOGIN  — 12345678
  [OK]  MT5_PASSWORD  — ***
  [OK]  MT5_SERVER  — XMTrading-Demo 3

[3] MT5 ターミナル初期化
  [OK]  mt5.initialize()

[4] アカウント情報
  [OK]  account_info()
     login        : 12345678
     server       : XMTrading-Demo 3
     balance      : 10000.00
     trade_mode   : DEMO
  [OK]  デモ口座であること  — デモです

[5] XAUUSD シンボル
  [OK]  symbol_info('XAUUSD')
  [OK]  最新ティック取得  — bid=2350.12 ask=2350.45 spread=0.33 USD

[6] 5分足データ取得
  [OK]  copy_rates (M5, 300本)  — 300本取得

[7] シグナル生成パイプライン
  [OK]  compute_features + generate_signal — side=FLAT

[8] アルゴ取引設定
  [OK]  AutoTrading 有効
```

### よくあるエラーと対処

| エラー | 原因 | 対処 |
|---|---|---|
| `mt5.initialize() failed (-10003)` | MT5アプリ未起動 | MT5を起動してログインしておく |
| `Authorization failed (-6)` | パスワード/サーバ違い | `.env` を再確認、サーバ名のスペースに注意 |
| `symbol_info('XAUUSD') 見つからず` | XMの銘柄表記が違う | 出力中の候補名を `config.py` の `symbol` に設定 |
| `AutoTrading 有効: NG` | アルゴ取引ボタンOFF | MT5上部の「アルゴリズム取引」を緑に |
| `最新ティック: 市場クローズ中` | 週末・取引時間外 | 平日の市場時間に再実行 (GOLDは月〜金) |

---

## ステップ 6: ドライラン (注文なしで動作確認)

```powershell
python live_trader.py --dry-run
```

5分ごとにシグナル判断のログが出ます:

```
2026-05-06 13:05:00 [INFO] Connected: account=12345678 ...
2026-05-06 13:05:00 [INFO] Loop started. dry_run=True
2026-05-06 13:05:30 [INFO] Bar 2026-05-06 13:00:00+00:00 close=2351.42 side=FLAT
2026-05-06 13:10:30 [INFO] Bar 2026-05-06 13:05:00+00:00 close=2352.18 side=LONG
2026-05-06 13:10:30 [INFO] ENTRY LONG lots=0.05 entry=2352.30 sl=2348.50 tp=2358.70
2026-05-06 13:10:30 [INFO] (dry_run) order skipped
```

これを **最低でも数日〜1週間** 流して、シグナル頻度や挙動を確認してください。

---

## ステップ 7: デモ実発注

ドライランで問題なければ:

```powershell
python live_trader.py
```

デモ口座にリアルタイムで注文が入ります。MT5アプリ画面の「ターミナル」→「取引」タブで保有ポジションが見えます。

> 止めたいときは `Ctrl+C`。保有ポジションは自動で閉じられないので、SL/TPで決済されるか、MT5アプリから手動で閉じてください。

---

## ステップ 8: 24時間運用 (任意)

ノートPCをずっと起動するのは現実的でないので:

- **Windows VPS** (XM公式VPS、ConoHa for Windows、Vultr Windows等) を月額で契約
- VPSにMT5 + Python + このプロジェクトを入れて `live_trader.py` を起動しっぱなし
- `nssm` 等で Windows サービス化すると自動再起動も可能

---

## チェックリスト

- [ ] XMデモ口座 開設・ログイン情報受領
- [ ] MT5 デスクトップアプリ インストール・ログイン成功
- [ ] アルゴリズム取引 ボタン有効化
- [ ] Python 3.10〜3.12 + 依存パッケージ インストール
- [ ] `.env` 作成・記入
- [ ] `python check_connection.py` 全項目OK
- [ ] `python live_trader.py --dry-run` で数日観察
- [ ] デモ実発注で数週間運用 → 結果を記録

すべて緑になってから、本番口座を考えてください (本番化を急ぐ理由はありません)。
