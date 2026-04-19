#!/usr/bin/env python3
"""
Shopify商品管理全自動化ツール

使い方:
  python shopify_manager.py create products.csv [--dry-run] [--variants]
  python shopify_manager.py update update.csv   [--dry-run] [--field price]
  python shopify_manager.py delete delete.csv   [--dry-run] [--force]
  python shopify_manager.py sync-inventory inventory.csv [--dry-run] [--location-id ID]
  python shopify_manager.py export --output export.csv [--status active] [--vendor ブランド名]

  # AI自動化コマンド
  python shopify_manager.py ai-generate products.csv [--dry-run] [--tags-only] [--desc-only] [--output-csv result.csv]
  python shopify_manager.py report --output report.csv [--ai-summary] [--low-stock 5]
  python shopify_manager.py optimize-price [--dry-run] [--ai] [--low-stock 5] [--high-stock 50]
  python shopify_manager.py schedule --start
  python shopify_manager.py schedule --list
  python shopify_manager.py schedule --run-now report
"""

import argparse
import os
import sys

from dotenv import load_dotenv

from shopify_client import ShopifyClient
from utils.logger import setup_logger

load_dotenv()
logger = setup_logger("shopify_manager")


def load_client() -> ShopifyClient:
    shop_name = (
        os.getenv("SHOPIFY_SHOP_NAME")
        or os.getenv("SHOPIFY_STORE")
        or ""
    ).strip()
    access_token = (
        os.getenv("SHOPIFY_ACCESS_TOKEN")
        or os.getenv("SHOPIFY_TOKEN")
        or ""
    ).strip()
    if not shop_name or not access_token:
        logger.error(
            ".envファイルにSHOPIFY_SHOP_NAME(またはSHOPIFY_STORE)と"
            "SHOPIFY_ACCESS_TOKEN(またはSHOPIFY_TOKEN)を設定してください"
        )
        sys.exit(1)
    return ShopifyClient(shop_name, access_token)


# ------------------------------------------------------------------ #
# 既存コマンドハンドラ
# ------------------------------------------------------------------ #

def cmd_create(args: argparse.Namespace) -> None:
    from commands.create import run_create
    client = None if args.dry_run else load_client()
    success, failed = run_create(
        args.csv_file,
        client,
        dry_run=args.dry_run,
        use_variants=args.variants,
        output_errors=args.output_errors,
    )
    sys.exit(1 if failed else 0)


def cmd_update(args: argparse.Namespace) -> None:
    from commands.update import run_update
    client = None if args.dry_run else load_client()
    success, failed = run_update(
        args.csv_file,
        client,
        dry_run=args.dry_run,
        field=args.field,
        output_errors=args.output_errors,
    )
    sys.exit(1 if failed else 0)


def cmd_delete(args: argparse.Namespace) -> None:
    from commands.delete import run_delete
    client = None if args.dry_run else load_client()
    success, failed = run_delete(
        args.csv_file,
        client,
        dry_run=args.dry_run,
        force=args.force,
        output_errors=args.output_errors,
    )
    sys.exit(1 if failed else 0)


def cmd_sync_inventory(args: argparse.Namespace) -> None:
    from commands.sync_inventory import run_sync_inventory
    client = None if args.dry_run else load_client()
    success, failed = run_sync_inventory(
        args.csv_file,
        client,
        location_id=args.location_id,
        dry_run=args.dry_run,
        output_errors=args.output_errors,
    )
    sys.exit(1 if failed else 0)


def cmd_export(args: argparse.Namespace) -> None:
    from commands.export import run_export
    client = load_client()
    count = run_export(
        args.output,
        client,
        status=args.status,
        product_type=args.product_type,
        vendor=args.vendor,
        limit=args.limit,
    )
    sys.exit(0 if count >= 0 else 1)


# ------------------------------------------------------------------ #
# AIコマンドハンドラ
# ------------------------------------------------------------------ #

def cmd_ai_generate(args: argparse.Namespace) -> None:
    from commands.ai_generate import run_ai_generate
    client = None if args.dry_run else load_client()
    success, failed = run_ai_generate(
        args.csv_file,
        client,
        dry_run=args.dry_run,
        tags_only=args.tags_only,
        desc_only=args.desc_only,
        output_csv=args.output_csv,
    )
    sys.exit(1 if failed else 0)


def cmd_report(args: argparse.Namespace) -> None:
    from commands.report import run_report
    client = load_client()
    count = run_report(
        args.output,
        client,
        ai_summary=args.ai_summary,
        low_stock_threshold=args.low_stock,
        status=args.status,
    )
    sys.exit(0 if count >= 0 else 1)


def cmd_optimize_price(args: argparse.Namespace) -> None:
    from commands.optimize_price import run_optimize_price
    client = None if args.dry_run else load_client()
    if args.dry_run:
        client = load_client()
    success, failed = run_optimize_price(
        client,
        dry_run=args.dry_run,
        use_ai=args.ai,
        low_stock=args.low_stock,
        high_stock=args.high_stock,
        low_stock_markup=args.markup,
        high_stock_discount=args.discount,
    )
    sys.exit(1 if failed else 0)


def cmd_schedule(args: argparse.Namespace) -> None:
    from commands.scheduler import run_scheduler
    run_scheduler(
        start=args.start,
        list_tasks=args.list,
        run_now=args.run_now,
    )


def cmd_gen_product(args: argparse.Namespace) -> None:
    from commands.digital_product_gen import run_gen_product
    client = None if args.dry_run else load_client()
    success, failed = run_gen_product(
        client,
        theme=args.theme,
        product_type=args.type,
        batch=args.batch,
        dry_run=args.dry_run,
        price=args.price,
    )
    sys.exit(1 if failed else 0)


def cmd_sns_post(args: argparse.Namespace) -> None:
    from commands.sns_auto import run_sns_post
    import os
    client = load_client() if (args.daily or args.product_id) else None
    store_url = os.getenv("SHOPIFY_STORE_URL", "")
    result = run_sns_post(
        product_id=args.product_id,
        theme=args.theme,
        dry_run=args.dry_run,
        daily=args.daily,
        store_url=store_url,
        client=client,
    )
    sys.exit(0 if result else 1)


def cmd_kpi(args: argparse.Namespace) -> None:
    from commands.kpi_dashboard import run_kpi_dashboard
    client = load_client()
    run_kpi_dashboard(
        client,
        period_days=args.period,
        output_path=args.output,
        use_ai=args.ai,
    )
    sys.exit(0)


# ------------------------------------------------------------------ #
# パーサー定義
# ------------------------------------------------------------------ #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shopify_manager",
        description="Shopify商品管理全自動化ツール",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- create ---
    p_create = sub.add_parser("create", help="CSVから商品を一括登録する")
    p_create.add_argument("csv_file", help="商品データCSVファイルのパス")
    p_create.add_argument("--dry-run", action="store_true", help="登録せずに変換結果を確認する")
    p_create.add_argument("--variants", action="store_true", help="複数バリアント形式のCSVを使用する")
    p_create.add_argument("--output-errors", metavar="FILE", help="失敗行を出力するCSVファイル")
    p_create.set_defaults(func=cmd_create)

    # --- update ---
    p_update = sub.add_parser("update", help="既存商品を一括更新する")
    p_update.add_argument("csv_file", help="更新データCSVファイルのパス")
    p_update.add_argument("--dry-run", action="store_true", help="更新せずに確認する")
    p_update.add_argument("--field", metavar="FIELD", help="特定フィールドのみ更新する (例: price)")
    p_update.add_argument("--output-errors", metavar="FILE", help="失敗行を出力するCSVファイル")
    p_update.set_defaults(func=cmd_update)

    # --- delete ---
    p_delete = sub.add_parser("delete", help="商品をアーカイブまたは削除する")
    p_delete.add_argument("csv_file", help="削除対象CSVファイルのパス")
    p_delete.add_argument("--dry-run", action="store_true", help="削除せずに確認する")
    p_delete.add_argument("--force", action="store_true", help="確認プロンプトをスキップする")
    p_delete.add_argument("--output-errors", metavar="FILE", help="失敗行を出力するCSVファイル")
    p_delete.set_defaults(func=cmd_delete)

    # --- sync-inventory ---
    p_sync = sub.add_parser("sync-inventory", help="在庫数を一括同期する")
    p_sync.add_argument("csv_file", help="在庫データCSVファイルのパス")
    p_sync.add_argument("--dry-run", action="store_true", help="更新せずに確認する")
    p_sync.add_argument("--location-id", type=int, metavar="ID", help="ShopifyロケーションID")
    p_sync.add_argument("--output-errors", metavar="FILE", help="失敗行を出力するCSVファイル")
    p_sync.set_defaults(func=cmd_sync_inventory)

    # --- export ---
    p_export = sub.add_parser("export", help="既存商品をCSVにエクスポートする")
    p_export.add_argument("--output", required=True, metavar="FILE", help="出力CSVファイルのパス")
    p_export.add_argument("--status", default="any", choices=["any", "active", "draft", "archived"],
                          help="フィルタリングするステータス")
    p_export.add_argument("--product-type", metavar="TYPE", help="商品タイプでフィルタリング")
    p_export.add_argument("--vendor", metavar="VENDOR", help="ベンダーでフィルタリング")
    p_export.add_argument("--limit", type=int, metavar="N", help="取得する最大商品数")
    p_export.set_defaults(func=cmd_export)

    # --- ai-generate ---
    p_ai = sub.add_parser("ai-generate", help="AIで商品説明・SEOタグを自動生成する")
    p_ai.add_argument("csv_file", help="商品データCSVファイルのパス")
    p_ai.add_argument("--dry-run", action="store_true", help="Shopifyに書き込まず確認のみ")
    p_ai.add_argument("--tags-only", action="store_true", help="タグのみ生成する")
    p_ai.add_argument("--desc-only", action="store_true", help="商品説明のみ生成する")
    p_ai.add_argument("--output-csv", metavar="FILE", help="生成結果を出力するCSVファイル")
    p_ai.set_defaults(func=cmd_ai_generate)

    # --- report ---
    p_report = sub.add_parser("report", help="在庫・商品状況のレポートを生成する")
    p_report.add_argument("--output", required=True, metavar="FILE", help="出力CSVファイルのパス")
    p_report.add_argument("--ai-summary", action="store_true", help="AIによるサマリーテキストも生成する")
    p_report.add_argument("--low-stock", type=int, default=5, metavar="N",
                          help="低在庫と判定する閾値 (デフォルト: 5)")
    p_report.add_argument("--status", default="any",
                          choices=["any", "active", "draft", "archived"],
                          help="フィルタリングするステータス")
    p_report.set_defaults(func=cmd_report)

    # --- optimize-price ---
    p_opt = sub.add_parser("optimize-price", help="在庫状況に基づいて価格を自動最適化する")
    p_opt.add_argument("--dry-run", action="store_true", help="変更せずに確認のみ")
    p_opt.add_argument("--ai", action="store_true", help="AIによる価格提案を使用する")
    p_opt.add_argument("--low-stock", type=int, default=5, metavar="N",
                       help="低在庫閾値 (デフォルト: 5)")
    p_opt.add_argument("--high-stock", type=int, default=50, metavar="N",
                       help="高在庫閾値 (デフォルト: 50)")
    p_opt.add_argument("--markup", type=float, default=0.10, metavar="RATE",
                       help="低在庫時の値上げ率 (デフォルト: 0.10 = 10%%)")
    p_opt.add_argument("--discount", type=float, default=0.10, metavar="RATE",
                       help="高在庫時の値下げ率 (デフォルト: 0.10 = 10%%)")
    p_opt.set_defaults(func=cmd_optimize_price)

    # --- schedule ---
    p_sched = sub.add_parser("schedule", help="自動タスクのスケジューラーを管理する")
    sched_group = p_sched.add_mutually_exclusive_group(required=True)
    sched_group.add_argument("--start", action="store_true", help="スケジューラーをデーモン起動する")
    sched_group.add_argument("--list", action="store_true", help="登録済みタスク一覧を表示する")
    sched_group.add_argument("--run-now", metavar="TASK",
                             choices=list({"report", "optimize-price", "gen-product", "sns-post", "kpi"}),
                             help="指定タスクを今すぐ実行する")
    p_sched.set_defaults(func=cmd_schedule)

    # --- gen-product ---
    p_gen = sub.add_parser("gen-product", help="AIでデジタル商品（プロンプト集・テンプレート）を自動生成・登録する")
    p_gen.add_argument("--theme", metavar="THEME", help="商品テーマ (例: 'ChatGPT副業プロンプト集')")
    p_gen.add_argument("--type", default="prompt_pack",
                       choices=["prompt_pack", "template", "guide"],
                       help="商品タイプ (デフォルト: prompt_pack)")
    p_gen.add_argument("--batch", type=int, default=1, metavar="N", help="まとめて生成する商品数")
    p_gen.add_argument("--price", type=int, metavar="YEN", help="価格を手動指定する (円)")
    p_gen.add_argument("--dry-run", action="store_true", help="Shopifyに登録せず確認のみ")
    p_gen.set_defaults(func=cmd_gen_product)

    # --- sns-post ---
    p_sns = sub.add_parser("sns-post", help="X(Twitter)に商品宣伝・教育コンテンツを自動投稿する")
    sns_group = p_sns.add_mutually_exclusive_group(required=True)
    sns_group.add_argument("--product-id", type=int, metavar="ID", help="投稿する商品ID")
    sns_group.add_argument("--theme", metavar="THEME", help="テーマから教育コンテンツ型ツイートを生成")
    sns_group.add_argument("--daily", action="store_true", help="売れ筋商品を自動選択して投稿")
    p_sns.add_argument("--dry-run", action="store_true", help="投稿せずにツイート文を確認のみ")
    p_sns.set_defaults(func=cmd_sns_post)

    # --- kpi ---
    p_kpi = sub.add_parser("kpi", help="売上KPIダッシュボードを表示する")
    p_kpi.add_argument("--period", type=int, default=30, metavar="DAYS",
                       help="集計期間（日数、デフォルト: 30）")
    p_kpi.add_argument("--output", metavar="FILE", help="KPIデータをCSVに出力")
    p_kpi.add_argument("--ai", action="store_true", help="AIによる改善提案を表示する")
    p_kpi.set_defaults(func=cmd_kpi)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
