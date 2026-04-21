"""飲食店向け 予約確認メール自動生成ツール

使い方の例:

    # 単体引数から 1 件生成（標準出力に表示）
    python reservation_email.py \
        --restaurant "和食 さくら" \
        --restaurant-phone "03-1234-5678" \
        --restaurant-address "東京都千代田区丸の内1-1-1" \
        --customer-name "山田 太郎" \
        --customer-email "taro@example.com" \
        --date 2026-05-01 --time 19:00 --party-size 4 \
        --course "季節のおまかせコース" \
        --notes "アレルギー: えび" \
        --reservation-id R-20260501-0001

    # CSV から一括生成し、out/ ディレクトリに .eml を書き出す
    python reservation_email.py --csv reservations_sample.csv --out-dir out

    # 生成と同時に SMTP で送信（環境変数で資格情報を設定）
    #   SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
    python reservation_email.py --csv reservations_sample.csv --send
"""

from __future__ import annotations

import argparse
import os
import smtplib
import sys
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

from utils.csv_handler import read_csv
from utils.logger import setup_logger

logger = setup_logger(__name__)

REQUIRED_FIELDS = [
    "restaurant",
    "restaurant_phone",
    "restaurant_address",
    "customer_name",
    "customer_email",
    "date",
    "time",
    "party_size",
]

WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]


@dataclass
class Reservation:
    restaurant: str
    restaurant_phone: str
    restaurant_address: str
    customer_name: str
    customer_email: str
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    party_size: int
    course: str = ""
    notes: str = ""
    reservation_id: str = ""
    cancel_deadline: str = ""
    seat: str = ""
    extras: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, row: dict) -> "Reservation":
        missing = [f for f in REQUIRED_FIELDS if not str(row.get(f, "")).strip()]
        if missing:
            raise ValueError(f"必須項目が不足しています: {', '.join(missing)}")
        try:
            party_size = int(str(row["party_size"]).strip())
        except ValueError as e:
            raise ValueError(f"party_size は整数で指定してください: {row['party_size']}") from e
        if party_size < 1:
            raise ValueError("party_size は 1 以上で指定してください")

        date_str = str(row["date"]).strip()
        time_str = str(row["time"]).strip()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"date は YYYY-MM-DD 形式で指定してください: {date_str}") from e
        try:
            datetime.strptime(time_str, "%H:%M")
        except ValueError as e:
            raise ValueError(f"time は HH:MM 形式で指定してください: {time_str}") from e

        known = set(cls.__dataclass_fields__.keys()) - {"extras"}
        extras = {k: v for k, v in row.items() if k not in known and v}
        base = {k: str(row.get(k, "")).strip() for k in known if k != "party_size"}
        return cls(party_size=party_size, extras=extras, **base)


def _format_date_ja(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{d.year}年{d.month}月{d.day}日 ({WEEKDAY_JA[d.weekday()]})"


def build_subject(r: Reservation) -> str:
    suffix = f" [予約番号: {r.reservation_id}]" if r.reservation_id else ""
    return f"【{r.restaurant}】ご予約ありがとうございます{suffix}"


def build_body(r: Reservation) -> str:
    lines: list[str] = []
    lines.append(f"{r.customer_name} 様")
    lines.append("")
    lines.append(f"このたびは {r.restaurant} にご予約いただき、誠にありがとうございます。")
    lines.append("以下の内容でご予約を承りましたので、ご確認をお願いいたします。")
    lines.append("")
    lines.append("―――――――――――――――――――――――")
    lines.append("■ ご予約内容")
    lines.append("―――――――――――――――――――――――")
    if r.reservation_id:
        lines.append(f"予約番号 : {r.reservation_id}")
    lines.append(f"ご来店日 : {_format_date_ja(r.date)}")
    lines.append(f"ご来店時間: {r.time}")
    lines.append(f"ご人数   : {r.party_size} 名様")
    if r.course:
        lines.append(f"コース   : {r.course}")
    if r.seat:
        lines.append(f"お席    : {r.seat}")
    if r.notes:
        lines.append(f"ご要望   : {r.notes}")
    for k, v in r.extras.items():
        lines.append(f"{k} : {v}")
    lines.append("")
    lines.append("―――――――――――――――――――――――")
    lines.append("■ 店舗情報")
    lines.append("―――――――――――――――――――――――")
    lines.append(f"店舗名  : {r.restaurant}")
    lines.append(f"住所   : {r.restaurant_address}")
    lines.append(f"電話番号 : {r.restaurant_phone}")
    lines.append("")
    lines.append("―――――――――――――――――――――――")
    lines.append("■ ご注意事項")
    lines.append("―――――――――――――――――――――――")
    if r.cancel_deadline:
        lines.append(f"・キャンセルは {r.cancel_deadline} までにご連絡ください。")
    else:
        lines.append("・ご都合が悪くなった場合は、お早めに店舗までご連絡ください。")
    lines.append("・ご来店時間を15分以上過ぎてもご連絡がない場合、キャンセル扱いとさせていただくことがございます。")
    lines.append("・アレルギー等ございましたら、事前にご連絡いただけますと幸いです。")
    lines.append("")
    lines.append(f"スタッフ一同、{r.customer_name} 様のお越しを心よりお待ちしております。")
    lines.append("")
    lines.append(f"{r.restaurant}")
    return "\n".join(lines)


def build_email(r: Reservation, sender: str | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = build_subject(r)
    msg["To"] = r.customer_email
    if sender:
        msg["From"] = sender
    msg.set_content(build_body(r))
    return msg


def _safe_filename(r: Reservation, index: int) -> str:
    key = r.reservation_id or f"{r.date}_{r.time.replace(':', '')}_{r.customer_name}"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    return f"{index:03d}_{safe}.eml"


def send_via_smtp(msg: EmailMessage) -> None:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM") or user
    if not (host and user and password and sender):
        raise RuntimeError(
            "SMTP 送信には SMTP_HOST / SMTP_USER / SMTP_PASSWORD / SMTP_FROM の環境変数が必要です"
        )
    if not msg["From"]:
        msg["From"] = sender
    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)


def _cli_row_from_args(args: argparse.Namespace) -> dict:
    return {
        "restaurant": args.restaurant,
        "restaurant_phone": args.restaurant_phone,
        "restaurant_address": args.restaurant_address,
        "customer_name": args.customer_name,
        "customer_email": args.customer_email,
        "date": args.date,
        "time": args.time,
        "party_size": args.party_size,
        "course": args.course or "",
        "notes": args.notes or "",
        "reservation_id": args.reservation_id or "",
        "cancel_deadline": args.cancel_deadline or "",
        "seat": args.seat or "",
    }


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="飲食店向け 予約確認メール自動生成ツール")
    p.add_argument("--csv", help="CSV から一括生成する場合のファイルパス")
    p.add_argument("--out-dir", help="生成した .eml の出力先ディレクトリ")
    p.add_argument("--send", action="store_true", help="SMTP で送信する")

    p.add_argument("--restaurant", help="店舗名")
    p.add_argument("--restaurant-phone", help="店舗の電話番号")
    p.add_argument("--restaurant-address", help="店舗の住所")
    p.add_argument("--customer-name", help="お客様のお名前")
    p.add_argument("--customer-email", help="お客様のメールアドレス")
    p.add_argument("--date", help="予約日 (YYYY-MM-DD)")
    p.add_argument("--time", help="予約時間 (HH:MM)")
    p.add_argument("--party-size", type=int, help="ご人数")
    p.add_argument("--course", help="コース名")
    p.add_argument("--seat", help="お席タイプ")
    p.add_argument("--notes", help="ご要望・備考")
    p.add_argument("--cancel-deadline", help="キャンセル期限 (表示用文字列)")
    p.add_argument("--reservation-id", help="予約番号")
    return p.parse_args()


def _process_row(row: dict, index: int, out_dir: Path | None, send: bool) -> bool:
    try:
        reservation = Reservation.from_dict(row)
    except ValueError as e:
        logger.error(f"[{index}] 入力エラー: {e}")
        return False

    msg = build_email(reservation, sender=os.environ.get("SMTP_FROM"))

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / _safe_filename(reservation, index)
        path.write_bytes(bytes(msg))
        logger.info(f"[{index}] 書き出し: {path}")
    else:
        print("=" * 60)
        print(f"To: {msg['To']}")
        print(f"Subject: {msg['Subject']}")
        print("-" * 60)
        print(msg.get_content())

    if send:
        try:
            send_via_smtp(msg)
            logger.info(f"[{index}] 送信成功: {reservation.customer_email}")
        except Exception as e:
            logger.error(f"[{index}] 送信失敗: {e}")
            return False
    return True


def main() -> int:
    load_dotenv()
    args = _parse_args()
    out_dir = Path(args.out_dir) if args.out_dir else None

    if args.csv:
        rows = read_csv(args.csv)
        if not rows:
            logger.error("CSV が空です")
            return 1
        logger.info(f"{len(rows)}件の予約を処理します")
        success, failed = 0, 0
        for i, row in enumerate(rows, start=1):
            if _process_row(row, i, out_dir, args.send):
                success += 1
            else:
                failed += 1
        logger.info(f"完了: 成功={success}件, 失敗={failed}件")
        return 0 if failed == 0 else 1

    missing = [f for f in REQUIRED_FIELDS if not getattr(args, f.replace("-", "_"), None)]
    if missing:
        logger.error(
            "--csv を指定しない場合、以下の引数が必要です: "
            + ", ".join("--" + f.replace("_", "-") for f in missing)
        )
        return 2

    row = _cli_row_from_args(args)
    ok = _process_row(row, 1, out_dir, args.send)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
