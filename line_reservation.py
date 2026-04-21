"""LINE 予約確認メッセージ自動送信スクリプト

CSV に書かれた予約情報を読み込み、LINE Messaging API の Push Message API で
お客様の LINE にメッセージを送信します。

2 つの送信モードがあります:
    - confirm  : 予約確認メッセージを全件に送信（既定）
    - reminder : 「翌日が予約日」のお客様にだけ前日リマインドを送信
                 （Windows のタスクスケジューラから毎日 18 時に呼び出す想定）

使い方:
    # 1) 依存パッケージをインストール
    #    pip install -r requirements.txt
    # 2) .env に LINE_CHANNEL_ACCESS_TOKEN を設定
    # 3) 実行（予約確認）
    #    python line_reservation.py
    # 3') 実行（前日リマインダー）
    #    python line_reservation.py --mode reminder
    # 動作確認用に日付を指定したい場合
    #    python line_reservation.py --mode reminder --target-date 2026-05-01
"""

# 標準ライブラリ（Python に最初から入っている機能）をインポート
import argparse  # コマンドライン引数を解析するため
import csv       # CSV ファイルを読み書きするため
import logging   # ログファイルに送信結果を記録するため
import os        # 環境変数を読むため
import sys       # 異常終了時に exit コードを返すため
from datetime import date, datetime, timedelta  # 日付計算のため
from pathlib import Path

# 外部ライブラリ（requirements.txt でインストールするもの）
import requests
from dotenv import load_dotenv


# ---------------------------------------------------------------
# 定数（プログラム内で使う固定値）
# ---------------------------------------------------------------

# LINE Messaging API の Push Message エンドポイント URL
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

# ログファイルの保存先
LOG_FILE = "logs/line_reservation.log"

# CSV の必須列（どれか一つでも欠けているとエラーにする）
REQUIRED_COLUMNS = [
    "店舗名",
    "電話番号",
    "顧客名",
    "予約日",
    "予約時間",
    "人数",
    "LINE_ユーザーID",
]


# ---------------------------------------------------------------
# ログ設定
# ---------------------------------------------------------------

def setup_logger() -> logging.Logger:
    """送信結果を記録するためのロガーを準備して返す。

    画面（コンソール）とファイルの両方に書き込む設定にしています。
    """
    # logs ディレクトリを作成（すでにあっても無視）
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("line_reservation")
    # 二重登録を防ぐため、既にハンドラが設定されていればそのまま返す
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # ログの表示フォーマット（時刻・レベル・メッセージ）
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # 画面に出力するハンドラ
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ファイルに出力するハンドラ
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# ---------------------------------------------------------------
# CSV 読み込み
# ---------------------------------------------------------------

def read_reservations(csv_path: str) -> list[dict]:
    """CSV ファイルを読み込み、予約情報のリスト（辞書の配列）を返す。

    Excel で保存した日本語 CSV は cp932（Shift_JIS）の場合があるため、
    utf-8-sig → utf-8 → cp932 の順で自動的に試します。
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV ファイルが見つかりません: {csv_path}")

    # 複数の文字コードを順に試す
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            with open(path, encoding=encoding) as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError(
        "utf-8", b"", 0, 1,
        f"CSV の文字コードを判別できませんでした: {csv_path}"
    )


def validate_columns(rows: list[dict]) -> None:
    """CSV に必須列がそろっているかチェックする。

    不足していれば例外を投げてプログラムを止めます。
    """
    if not rows:
        raise ValueError("CSV にデータが 1 件もありません")

    headers = set(rows[0].keys())
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        raise ValueError(
            f"CSV に必須列が不足しています: {', '.join(missing)}"
        )


# ---------------------------------------------------------------
# メッセージ生成
# ---------------------------------------------------------------

def _extract_fields(reservation: dict) -> dict:
    """予約 dict から本文生成で使う値だけを取り出し、前後の空白を削る。"""
    # .get(キー, "") で、値がなければ空文字になるようにしている
    return {
        "customer_name": reservation.get("顧客名", "").strip(),
        "restaurant": reservation.get("店舗名", "").strip(),
        "reservation_date": reservation.get("予約日", "").strip(),
        "reservation_time": reservation.get("予約時間", "").strip(),
        "party_size": reservation.get("人数", "").strip(),
        "phone": reservation.get("電話番号", "").strip(),
    }


def build_confirm_message(reservation: dict) -> str:
    """予約確認メッセージの本文を作って返す。"""
    f = _extract_fields(reservation)
    # 複数行の文字列は """...""" で書けます（f"""...""" で変数も埋め込めます）
    return f"""{f['customer_name']}様

この度はご予約いただきありがとうございます。
以下の内容でご予約を承りました。

■ 店舗名：{f['restaurant']}
■ 日時：{f['reservation_date']} {f['reservation_time']}
■ 人数：{f['party_size']}名様

ご来店をお待ちしております。
ご不明な点は {f['phone']} までお気軽にご連絡ください。"""


def build_reminder_message(reservation: dict) -> str:
    """前日リマインダーメッセージの本文を作って返す。"""
    f = _extract_fields(reservation)
    return f"""{f['customer_name']}様

明日のご予約のリマインドです。

■ 日時：{f['reservation_date']} {f['reservation_time']}
■ 人数：{f['party_size']}名様
■ 店舗：{f['restaurant']}（{f['phone']}）

ご来店をお待ちしております。
キャンセル・変更の場合はお早めにご連絡ください。"""


# 旧 API 互換用（外部から build_message を呼んでいるコードがあれば動くように残す）
build_message = build_confirm_message


# ---------------------------------------------------------------
# リマインダー用の日付フィルタ
# ---------------------------------------------------------------

def _parse_reservation_date(value: str) -> date | None:
    """予約日の文字列を date に変換する。

    CSV でよく使われる以下のフォーマットを順に試します。
    変換できなければ None（= リマインダー対象外）を返します。
        2026-05-01 / 2026/05/01 / 2026.05.01
    """
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def filter_tomorrow(reservations: list[dict], today: date) -> list[dict]:
    """「翌日が予約日」の予約だけを抜き出して返す。"""
    tomorrow = today + timedelta(days=1)
    result: list[dict] = []
    for r in reservations:
        d = _parse_reservation_date(r.get("予約日", ""))
        if d is not None and d == tomorrow:
            result.append(r)
    return result


# ---------------------------------------------------------------
# LINE 送信
# ---------------------------------------------------------------

def send_line_message(
    access_token: str,
    user_id: str,
    message: str,
    timeout: int = 10,
) -> None:
    """LINE Messaging API の Push Message で 1 通送信する。

    送信に失敗した場合は例外を投げます（呼び出し側で except して次に進む想定）。
    """
    # HTTP リクエストのヘッダ（認証情報と Content-Type）
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Push Message API が要求する JSON 形式
    # 参考: https://developers.line.biz/ja/reference/messaging-api/#send-push-message
    payload = {
        "to": user_id,
        "messages": [
            {"type": "text", "text": message},
        ],
    }

    response = requests.post(
        LINE_PUSH_URL,
        headers=headers,
        json=payload,
        timeout=timeout,
    )

    # ステータスコードが 200 番台以外の場合は例外を投げる
    if response.status_code >= 400:
        raise requests.HTTPError(
            f"LINE API エラー: status={response.status_code}, body={response.text}"
        )


# ---------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------

def main() -> int:
    # .env ファイルがあれば読み込む（存在しなくても無視される）
    load_dotenv()

    # コマンドライン引数を解析
    parser = argparse.ArgumentParser(description="LINE 予約確認メッセージ送信ツール")
    parser.add_argument(
        "--csv",
        default="reservations.csv",
        help="予約情報が書かれた CSV ファイルのパス（既定: reservations.csv）",
    )
    parser.add_argument(
        "--mode",
        choices=["confirm", "reminder"],
        default="confirm",
        help=(
            "送信モード: "
            "confirm=予約確認を全件送信（既定）、"
            "reminder=翌日予約のお客様にだけ前日リマインドを送信"
        ),
    )
    parser.add_argument(
        "--target-date",
        help=(
            "reminder モードの基準日 (YYYY-MM-DD)。"
            "この日付の「翌日」が予約日の予約が送信対象になります。"
            "省略時は今日の日付（タスクスケジューラ運用時は省略推奨）。"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際に送信せず、送信内容だけ表示する（動作確認用）",
    )
    args = parser.parse_args()

    logger = setup_logger()

    # 環境変数からアクセストークンを取得
    access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not access_token and not args.dry_run:
        logger.error(
            "環境変数 LINE_CHANNEL_ACCESS_TOKEN が設定されていません。"
            " .env を確認してください。"
        )
        return 1

    # CSV を読み込み＆バリデーション
    try:
        reservations = read_reservations(args.csv)
        validate_columns(reservations)
    except (FileNotFoundError, ValueError, UnicodeDecodeError) as e:
        logger.error(f"CSV 読み込みエラー: {e}")
        return 1

    # reminder モードなら「翌日が予約日」のものだけに絞り込む
    if args.mode == "reminder":
        # --target-date が指定されていればその日付、なければ今日を基準にする
        if args.target_date:
            try:
                today = datetime.strptime(args.target_date, "%Y-%m-%d").date()
            except ValueError:
                logger.error(
                    f"--target-date は YYYY-MM-DD 形式で指定してください: {args.target_date}"
                )
                return 1
        else:
            today = date.today()

        tomorrow = today + timedelta(days=1)
        reservations = filter_tomorrow(reservations, today)
        logger.info(
            f"リマインダー対象: {tomorrow.isoformat()} の予約 {len(reservations)}件"
            f"（基準日: {today.isoformat()}）"
        )

        # メッセージ生成関数を差し替え
        build_fn = build_reminder_message
    else:
        build_fn = build_confirm_message

    total = len(reservations)
    logger.info(
        f"{total}件の予約を処理します (mode={args.mode}, dry_run={args.dry_run})"
    )

    # 対象 0 件のときは早めに終了（リマインダー運用で毎日 18 時に実行される想定）
    if total == 0:
        print("送信完了：0件")
        return 0

    # 送信件数をカウントする変数
    success_count = 0
    failed_count = 0

    # 予約を 1 件ずつ処理する
    # enumerate の start=1 は「1 行目から」数えるという意味
    for index, reservation in enumerate(reservations, start=1):
        customer = reservation.get("顧客名", "").strip()
        user_id = reservation.get("LINE_ユーザーID", "").strip()

        # LINE ユーザー ID が空ならスキップ
        if not user_id:
            logger.warning(f"[{index}/{total}] {customer}: LINE_ユーザーID が空のためスキップ")
            failed_count += 1
            continue

        # メッセージを生成（モードに応じて confirm / reminder が切り替わる）
        message = build_fn(reservation)

        # --dry-run モードは送信せずに内容だけ表示
        if args.dry_run:
            logger.info(f"[{index}/{total}] [DRY-RUN] 送信予定: {customer} ({user_id})")
            logger.info("\n" + message)
            success_count += 1
            continue

        # 実際に送信。失敗しても次に進む（続行性を優先）
        try:
            send_line_message(access_token, user_id, message)
            logger.info(f"[{index}/{total}] 送信成功: {customer} ({user_id})")
            success_count += 1
        except Exception as e:
            # どんな例外でも拾って次の予約に進む
            logger.error(f"[{index}/{total}] 送信失敗: {customer} ({user_id}) - {e}")
            failed_count += 1
            continue

    # 最終結果を表示
    # ユーザー指定の仕様通り「送信完了：X件」を出力
    print(f"送信完了：{success_count}件")
    if failed_count:
        print(f"送信失敗：{failed_count}件（詳細は {LOG_FILE} を参照）")

    return 0


# このファイルを直接実行したときだけ main() を呼ぶ
if __name__ == "__main__":
    sys.exit(main())
