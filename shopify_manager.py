#!/usr/bin/env python3
"""
Shopify商品管理全自動化ツール

使い方:
  python shopify_manager.py create products.csv [--dry-run] [--variants]
  python shopify_manager.py update update.csv   [--dry-run] [--field price]
  python shopify_manager.py delete delete.csv   [--dry-run] [--force]
  python shopify_manager.py sync-inventory inventory.csv [--dry-run] [--location-id ID]
  python shopify_manager.py export --output export.csv [--status active] [--vendor ブランド名]
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
    # SHOPIFY_STORE / SHOPIFY_TOKEN も別名として受け付ける
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
# サブコマンドハンドラ
# ------------------------------------------------------------------ #

def cmd_create(args: argparse.Namespace) -> None:
    from commands.create import run_create
    client = load_client()
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
    client = load_client()
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
    client = load_client()
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
    client = load_client()
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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
