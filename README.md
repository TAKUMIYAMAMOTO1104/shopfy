# LINE 予約確認メッセージ自動送信ツール

飲食店の予約情報を記録した CSV ファイルを読み込み、**LINE Messaging API の Push Message API** を使って
お客様の LINE に予約確認メッセージを自動送信するスクリプトです。

## ファイル構成

| ファイル                 | 役割                               |
| ------------------------ | ---------------------------------- |
| `line_reservation.py`    | メインスクリプト                   |
| `reservations.csv`       | 送信対象の予約データ（サンプル付き）|
| `.env.example`           | 環境変数のサンプル                 |
| `logs/line_reservation.log` | 送信結果のログ（実行時に自動生成） |

## 事前準備

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

`requests` と `python-dotenv` を使います。

### 2. LINE チャネルアクセストークンの取得

1. [LINE Developers](https://developers.line.biz/console/) にログイン
2. **Messaging API チャネル** を作成（または既存のチャネルを開く）
3. 「Messaging API 設定」タブ →「チャネルアクセストークン」→ **「発行」** を押してトークンを取得

### 3. 環境変数の設定

`.env.example` をコピーして `.env` を作り、発行したトークンを貼り付けます。

```bash
cp .env.example .env
```

`.env` の該当行を書き換えます。

```
LINE_CHANNEL_ACCESS_TOKEN=あなたのチャネルアクセストークン
```

> `.env` は `.gitignore` に入っているので、Git にコミットされません（トークンの漏洩防止）。

### 4. 送信先 LINE ユーザー ID の用意

LINE Messaging API で Push 送信する相手は、**あなたの LINE 公式アカウントを友だち追加しているユーザー** に限ります。
ユーザー ID（`U` から始まる 33 文字の文字列）は、Webhook イベントや管理画面から取得できます。

## CSV の形式

列の順序は自由ですが、以下の列（ヘッダ名）が **必須** です。

| 列名             | 例                                   |
| ---------------- | ------------------------------------ |
| 店舗名           | 和食 さくら                          |
| 電話番号         | 03-1234-5678                         |
| 顧客名           | 山田 太郎                            |
| 予約日           | 2026-05-01                           |
| 予約時間         | 19:00                                |
| 人数             | 4                                    |
| LINE_ユーザーID  | U1234567890abcdef1234567890abcdef    |

`reservations.csv` に 3 件のサンプルが入っています（ユーザー ID はダミー）。

## 使い方

このツールには 2 つの送信モードがあります。

| モード          | コマンド                                     | 送る内容                                                   |
| --------------- | -------------------------------------------- | ---------------------------------------------------------- |
| 予約確認 (既定) | `python line_reservation.py`                 | CSV の全予約に予約確認メッセージを送信                     |
| 前日リマインダー| `python line_reservation.py --mode reminder` | 「翌日が予約日」の予約にだけリマインドメッセージを送信     |

### 本番運用前のテスト

本番送信する前に、以下 2 段階で動作確認することを推奨します。

| フラグ         | 送信する？ | 範囲               | 目的                                             |
| -------------- | ---------- | ------------------ | ------------------------------------------------ |
| `--test`       | しない     | 全件               | 文面が意図通りか目視チェック（社内用確認）       |
| `--send-test`  | する       | CSV の 1 件目のみ  | LINE API まで実際に疎通するかエンドツーエンド確認 |

```bash
# ① 送信予定メッセージをコンソールに表示（実送信なし）
python line_reservation.py --csv reservations.csv --test

# ② CSV の 1 件目だけ実際に送信して疎通確認
python line_reservation.py --csv reservations.csv --send-test
```

- `--test` と `--send-test` は **同時指定できません**（argparse が拒否します）。
- `--send-test` は本物のアクセストークンが必要です（`.env` を忘れずに）。
- reminder モードと組み合わせると、メッセージ本文はリマインド版になります。
  - `python line_reservation.py --mode reminder --test` … 明日予約のお客様への文面を確認
  - `python line_reservation.py --mode reminder --send-test` … 日付フィルタを無視して CSV 1 件目に実送信
- 後方互換のため `--dry-run` も `--test` と同じ意味で引き続き使えます。

### 実際に送信（予約確認）

```bash
python line_reservation.py
```

別の CSV を使いたい場合は `--csv` で指定できます。

```bash
python line_reservation.py --csv my_reservations.csv
```

### 前日リマインダーの送信

実行した日の **翌日** が予約日になっているお客様だけにリマインドを送ります。

```bash
python line_reservation.py --mode reminder
```

動作確認用に基準日を指定することもできます（`--target-date` の翌日が対象になります）。

```bash
python line_reservation.py --mode reminder --target-date 2026-04-30 --dry-run
```

## 送信されるメッセージ

### 予約確認（`--mode confirm`、既定）

```
山田 太郎様

この度はご予約いただきありがとうございます。
以下の内容でご予約を承りました。

■ 店舗名：和食 さくら
■ 日時：2026-05-01 19:00
■ 人数：4名様

ご来店をお待ちしております。
ご不明な点は 03-1234-5678 までお気軽にご連絡ください。
```

### 前日リマインダー（`--mode reminder`）

```
山田 太郎様

明日のご予約のリマインドです。

■ 日時：2026-05-01 19:00
■ 人数：4名様
■ 店舗：和食 さくら（03-1234-5678）

ご来店をお待ちしております。
キャンセル・変更の場合はお早めにご連絡ください。
```

## Windows タスクスケジューラで毎日 18 時に自動実行する

前日リマインダーは、Windows のタスクスケジューラから毎日 18 時に
`--mode reminder` で自動実行するのが想定運用です。

### 手順

1. **実行用のバッチファイルを作成**

   スクリプトのあるフォルダ（例: `C:\shopfy`）に `send_reminder.bat` を作り、
   以下を貼り付けます。パスは環境に合わせて書き換えてください。

   ```bat
   @echo off
   REM 文字化け防止に UTF-8 に切り替え
   chcp 65001 > nul

   REM 作業ディレクトリを .py のあるフォルダに移動
   cd /d C:\shopfy

   REM Python で前日リマインダーを実行
   python line_reservation.py --mode reminder >> logs\reminder_stdout.log 2>&1
   ```

   > venv を使っている場合は `python` の代わりに `C:\shopfy\.venv\Scripts\python.exe` のように
   > 絶対パスを指定すると確実です。

2. **タスクスケジューラを開く**

   スタートメニューで「タスク スケジューラ」を検索して起動します。

3. **タスクの作成**（「基本タスクの作成」ではなく「**タスクの作成**」を選ぶと細かい設定ができます）

   - **[全般]** タブ
     - 名前: `LINE 予約リマインダー`
     - 「ユーザーがログオンしているかどうかにかかわらず実行する」にチェック
     - 「最上位の特権で実行する」にチェック（推奨）
   - **[トリガー]** タブ →「新規」
     - 開始: **毎日 18:00**
     - 間隔: 1 日
     - 有効にチェック
   - **[操作]** タブ →「新規」
     - 操作: `プログラムの開始`
     - プログラム/スクリプト: `C:\shopfy\send_reminder.bat`
     - 開始（オプション）: `C:\shopfy` ← **必ず指定**（相対パス解決のため）
   - **[条件]** タブ
     - 「コンピューターを AC 電源で使用している場合のみタスクを開始する」のチェックは
       必要に応じて外す（ノート PC で電源不安定な場合）
   - **[設定]** タブ
     - 「タスクを要求時に実行する」にチェック
     - 「タスクが失敗した場合の再起動の間隔」を 10 分・3 回などに設定しておくと安心

4. **動作テスト**

   作成したタスクを右クリック →「**実行**」で即時起動できます。
   `logs\line_reservation.log` と `logs\reminder_stdout.log` に出力が残ることを
   確認してください。

### PowerShell で一発登録したい場合（上級者向け）

管理者権限の PowerShell で以下を実行すると、GUI を触らずに登録できます。

```powershell
$action   = New-ScheduledTaskAction -Execute "C:\shopfy\send_reminder.bat" -WorkingDirectory "C:\shopfy"
$trigger  = New-ScheduledTaskTrigger -Daily -At 18:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "LINE 予約リマインダー" `
    -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest
```

### うまく動かないときのチェックリスト

- [ ] バッチファイルを **手動でダブルクリック** して動くか確認した
- [ ] タスクの「開始（オプション）」に作業フォルダを指定した
- [ ] `.env` がスクリプトと同じフォルダにある
- [ ] Python が PATH に通っているか、または絶対パスで指定している
- [ ] `logs\reminder_stdout.log` にエラーが出ていないか確認した

## 動作の特徴

- **エラーで止まらない**: 1 件の送信でエラーが出ても、次の予約へ進みます。
- **ログに全件記録**: 送信成功／失敗が `logs/line_reservation.log` に残ります。
- **完了時に件数表示**: 最後に `送信完了：X件` を表示します（失敗があれば失敗件数も表示）。

## よくあるエラー

| エラーメッセージ                                       | 原因・対処                                          |
| ------------------------------------------------------ | --------------------------------------------------- |
| `環境変数 LINE_CHANNEL_ACCESS_TOKEN が設定されていません` | `.env` にトークンを書いたか確認してください         |
| `LINE API エラー: status=401`                          | トークンが無効／期限切れ。再発行してください        |
| `LINE API エラー: status=400`                          | ユーザー ID が間違っている、または友だち未追加です  |
| `CSV ファイルが見つかりません`                         | `--csv` で指定したパスを確認してください            |
| `CSV に必須列が不足しています`                         | ヘッダ名を上の表のとおりに修正してください          |
