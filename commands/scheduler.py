"""定期実行スケジューラー

バックグラウンドで自動タスクを定期実行する。

使い方:
  python shopify_manager.py schedule --start           # スケジューラー起動
  python shopify_manager.py schedule --list            # 登録済みタスク一覧
  python shopify_manager.py schedule --run-now TASK    # 手動即時実行

環境変数でスケジュールを制御:
  SCHEDULE_REPORT_HOUR=9          # レポート生成時刻 (デフォルト: 9時)
  SCHEDULE_OPTIMIZE_DAY=monday    # 価格最適化曜日 (デフォルト: monday)
  SCHEDULE_REPORT_OUTPUT=reports/ # レポート出力ディレクトリ
"""
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from utils.logger import setup_logger

logger = setup_logger(__name__)

TASKS = {
    "report": "在庫・売上レポートを生成してCSVに保存",
    "optimize-price": "在庫状況に応じて価格を自動調整",
    "ai-generate": "未記入商品にAI説明文を自動生成",
}


def run_scheduler(start: bool = False, list_tasks: bool = False, run_now: str | None = None) -> None:
    if list_tasks:
        _print_tasks()
        return

    if run_now:
        _execute_task(run_now)
        return

    if start:
        _start_daemon()


def _print_tasks() -> None:
    logger.info("登録済み自動タスク:")
    report_hour = int(os.getenv("SCHEDULE_REPORT_HOUR", "9"))
    optimize_day = os.getenv("SCHEDULE_OPTIMIZE_DAY", "monday")
    for name, desc in TASKS.items():
        if name == "report":
            logger.info(f"  [{name}] {desc} — 毎日 {report_hour:02d}:00")
        elif name == "optimize-price":
            logger.info(f"  [{name}] {desc} — 毎週{_day_ja(optimize_day)}")
        else:
            logger.info(f"  [{name}] {desc} — 手動実行のみ")


def _start_daemon() -> None:
    try:
        import schedule
    except ImportError:
        logger.error("scheduleパッケージが必要です: pip install schedule")
        sys.exit(1)

    report_hour = int(os.getenv("SCHEDULE_REPORT_HOUR", "9"))
    optimize_day = os.getenv("SCHEDULE_OPTIMIZE_DAY", "monday")

    logger.info("スケジューラーを起動します。Ctrl+C で停止。")
    _print_tasks()

    schedule.every().day.at(f"{report_hour:02d}:00").do(_execute_task, "report")
    getattr(schedule.every(), optimize_day).at("10:00").do(_execute_task, "optimize-price")

    while True:
        schedule.run_pending()
        time.sleep(30)


def _execute_task(task_name: str) -> None:
    import os
    from dotenv import load_dotenv

    load_dotenv()

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    logger.info(f"[スケジューラー] タスク開始: {task_name} ({ts})")

    shop_name = (os.getenv("SHOPIFY_SHOP_NAME") or os.getenv("SHOPIFY_STORE") or "").strip()
    access_token = (os.getenv("SHOPIFY_ACCESS_TOKEN") or os.getenv("SHOPIFY_TOKEN") or "").strip()

    if not shop_name or not access_token:
        logger.error("Shopify認証情報が設定されていません (.env を確認)")
        return

    try:
        from shopify_client import ShopifyClient
        client = ShopifyClient(shop_name, access_token)

        if task_name == "report":
            _run_report_task(client, ts)
        elif task_name == "optimize-price":
            _run_optimize_task(client)
        else:
            logger.warning(f"未知のタスク: {task_name}")
    except Exception as e:
        logger.error(f"タスク実行エラー ({task_name}): {e}")


def _run_report_task(client, ts: str) -> None:
    from commands.report import run_report

    output_dir = Path(os.getenv("SCHEDULE_REPORT_OUTPUT", "reports"))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / f"report_{ts}.csv")
    ai_summary = os.getenv("SCHEDULE_AI_SUMMARY", "true").lower() == "true"
    low_stock = int(os.getenv("SCHEDULE_LOW_STOCK_THRESHOLD", "5"))

    count = run_report(output_path, client, ai_summary=ai_summary, low_stock_threshold=low_stock)
    logger.info(f"[スケジューラー] レポート完了: {output_path} ({count}件)")


def _run_optimize_task(client) -> None:
    from commands.optimize_price import run_optimize_price

    low_stock = int(os.getenv("SCHEDULE_LOW_STOCK_THRESHOLD", "5"))
    high_stock = int(os.getenv("SCHEDULE_HIGH_STOCK_THRESHOLD", "50"))
    markup = float(os.getenv("SCHEDULE_LOW_STOCK_MARKUP", "0.10"))
    discount = float(os.getenv("SCHEDULE_HIGH_STOCK_DISCOUNT", "0.10"))
    use_ai = os.getenv("SCHEDULE_AI_PRICE", "false").lower() == "true"

    success, failed = run_optimize_price(
        client,
        dry_run=False,
        use_ai=use_ai,
        low_stock=low_stock,
        high_stock=high_stock,
        low_stock_markup=markup,
        high_stock_discount=discount,
    )
    logger.info(f"[スケジューラー] 価格最適化完了: 成功={success}, 失敗={failed}")


def _day_ja(day: str) -> str:
    mapping = {
        "monday": "月曜", "tuesday": "火曜", "wednesday": "水曜",
        "thursday": "木曜", "friday": "金曜", "saturday": "土曜", "sunday": "日曜",
    }
    return mapping.get(day.lower(), day)
