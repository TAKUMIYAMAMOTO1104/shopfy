#!/usr/bin/env python3
"""
Shopify商品一括登録スクリプト
CSVファイルから商品データを読み込み、Shopify Admin APIで登録します。

使い方:
  python upload_products.py products.csv
  python upload_products.py products.csv --dry-run   # 登録せず確認のみ
"""

import csv
import json
import os
import sys
import time
import argparse
import logging
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("upload_products.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"title", "price"}
API_VERSION = "2024-01"
RATE_LIMIT_DELAY = 0.5  # Shopify REST APIのレート制限対策 (500ms)


class ShopifyClient:
    def __init__(self, shop_name: str, access_token: str):
        self.base_url = f"https://{shop_name}.myshopify.com/admin/api/{API_VERSION}"
        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }

    def create_product(self, product_data: dict) -> dict:
        url = f"{self.base_url}/products.json"
        resp = requests.post(url, headers=self.headers, json={"product": product_data}, timeout=30)
        resp.raise_for_status()
        return resp.json()["product"]

    def upload_image(self, product_id: int, image_url: str) -> None:
        url = f"{self.base_url}/products/{product_id}/images.json"
        payload = {"image": {"src": image_url}}
        resp = requests.post(url, headers=self.headers, json=payload, timeout=30)
        resp.raise_for_status()


def parse_product_row(row: dict) -> dict:
    """CSVの1行をShopify商品ペイロードに変換する"""
    variant = {
        "price": row["price"],
        "inventory_management": "shopify",
    }

    if row.get("compare_at_price"):
        variant["compare_at_price"] = row["compare_at_price"]
    if row.get("sku"):
        variant["sku"] = row["sku"]
    if row.get("inventory_quantity"):
        variant["inventory_quantity"] = int(row["inventory_quantity"])
    if row.get("weight"):
        variant["weight"] = float(row["weight"])
        variant["weight_unit"] = "kg"

    product = {
        "title": row["title"],
        "variants": [variant],
        "published": True,
    }

    if row.get("body_html"):
        product["body_html"] = row["body_html"]
    if row.get("vendor"):
        product["vendor"] = row["vendor"]
    if row.get("product_type"):
        product["product_type"] = row["product_type"]
    if row.get("tags"):
        product["tags"] = row["tags"]

    return product


def validate_csv(rows: list[dict]) -> list[str]:
    """CSVデータのバリデーション。エラーメッセージのリストを返す"""
    errors = []
    headers = set(rows[0].keys()) if rows else set()
    missing = REQUIRED_COLUMNS - headers
    if missing:
        errors.append(f"必須列が不足しています: {', '.join(missing)}")
        return errors

    for i, row in enumerate(rows, start=2):
        if not row.get("title"):
            errors.append(f"行{i}: titleが空です")
        if not row.get("price"):
            errors.append(f"行{i}: priceが空です")
        try:
            if row.get("price"):
                float(row["price"])
        except ValueError:
            errors.append(f"行{i}: priceが数値ではありません ({row['price']})")

    return errors


def upload_products(csv_path: str, dry_run: bool = False) -> None:
    shop_name = os.getenv("SHOPIFY_SHOP_NAME")
    access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")

    if not shop_name or not access_token:
        logger.error(".envファイルにSHOPIFY_SHOP_NAMEとSHOPIFY_ACCESS_TOKENを設定してください")
        sys.exit(1)

    path = Path(csv_path)
    if not path.exists():
        logger.error(f"CSVファイルが見つかりません: {csv_path}")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        logger.warning("CSVにデータがありません")
        return

    errors = validate_csv(rows)
    if errors:
        for e in errors:
            logger.error(e)
        sys.exit(1)

    logger.info(f"{len(rows)}件の商品を処理します (dry_run={dry_run})")

    if dry_run:
        for i, row in enumerate(rows, start=1):
            product = parse_product_row(row)
            logger.info(f"[DRY-RUN] 商品{i}: {json.dumps(product, ensure_ascii=False)}")
        return

    client = ShopifyClient(shop_name, access_token)
    success, failed = 0, 0

    for i, row in enumerate(rows, start=1):
        title = row.get("title", "")
        try:
            product_data = parse_product_row(row)
            created = client.create_product(product_data)
            product_id = created["id"]
            logger.info(f"[{i}/{len(rows)}] 登録成功: {title} (ID: {product_id})")

            if row.get("image_url"):
                try:
                    client.upload_image(product_id, row["image_url"])
                    logger.info(f"  画像アップロード完了: {row['image_url']}")
                except requests.HTTPError as e:
                    logger.warning(f"  画像アップロード失敗 (商品登録は成功): {e}")

            success += 1
        except requests.HTTPError as e:
            logger.error(f"[{i}/{len(rows)}] 登録失敗: {title} - {e.response.text}")
            failed += 1
        except Exception as e:
            logger.error(f"[{i}/{len(rows)}] 予期しないエラー: {title} - {e}")
            failed += 1

        time.sleep(RATE_LIMIT_DELAY)

    logger.info(f"完了: 成功={success}, 失敗={failed}")
    if failed:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Shopify商品一括登録ツール")
    parser.add_argument("csv_file", help="商品データCSVファイルのパス")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="APIには登録せず、変換結果のみ確認する",
    )
    args = parser.parse_args()
    upload_products(args.csv_file, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
