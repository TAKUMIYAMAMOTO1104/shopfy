"""AI商品説明・タグ自動生成コマンド

使い方:
  python shopify_manager.py ai-generate products.csv [--dry-run] [--tags-only] [--desc-only]
"""
import time

from shopify_client import ShopifyClient
from utils.ai_client import generate_product_description, generate_seo_tags
from utils.csv_handler import read_csv, write_csv
from utils.logger import setup_logger

logger = setup_logger(__name__)


def run_ai_generate(
    csv_path: str,
    client: ShopifyClient | None,
    dry_run: bool = False,
    tags_only: bool = False,
    desc_only: bool = False,
    output_csv: str | None = None,
) -> tuple[int, int]:
    rows = read_csv(csv_path)
    if not rows:
        logger.error("CSVにデータがありません")
        return 0, 0

    total = len(rows)
    logger.info(f"{total}件の商品のAI生成を開始します (dry_run={dry_run})")

    success, failed = 0, 0
    output_rows: list[dict] = []

    for i, row in enumerate(rows, start=1):
        title = row.get("title", "").strip()
        if not title:
            logger.warning(f"行{i + 1}: titleが空のためスキップ")
            failed += 1
            continue

        product_id = row.get("product_id", "").strip()
        product_type = row.get("product_type", "")
        vendor = row.get("vendor", "")
        existing_tags = row.get("tags", "")
        price = row.get("price", "")

        try:
            new_desc = ""
            new_tags = ""

            if not tags_only:
                logger.info(f"[{i}/{total}] '{title}' の商品説明を生成中...")
                new_desc = generate_product_description(
                    title, product_type, vendor, existing_tags, price
                )

            if not desc_only:
                logger.info(f"[{i}/{total}] '{title}' のSEOタグを生成中...")
                new_tags = generate_seo_tags(title, product_type, vendor, existing_tags)

            if dry_run:
                logger.info(f"[DRY-RUN] {title}")
                if new_desc:
                    logger.info(f"  説明: {new_desc[:80]}...")
                if new_tags:
                    logger.info(f"  タグ: {new_tags}")
                output_rows.append({**row, "body_html": new_desc, "tags": new_tags})
                success += 1
                continue

            if not product_id:
                logger.warning(f"[{i}/{total}] product_idがないためShopify更新をスキップ (CSVに出力のみ)")
                output_rows.append({**row, "body_html": new_desc, "tags": new_tags})
                success += 1
                continue

            # Shopify更新
            update_data: dict = {}
            if new_desc:
                update_data["body_html"] = new_desc
            if new_tags:
                update_data["tags"] = new_tags

            if update_data and client:
                client.update_product(int(product_id), update_data)
                logger.info(f"[{i}/{total}] 更新完了: {title} (ID: {product_id})")

            output_rows.append({**row, "body_html": new_desc, "tags": new_tags})
            success += 1

        except Exception as e:
            logger.error(f"[{i}/{total}] 失敗: {title} - {e}")
            output_rows.append(row)
            failed += 1

        # API制限対策
        if i < total:
            time.sleep(0.5)

    logger.info(f"完了: 成功={success}件, 失敗={failed}件")

    if output_csv and output_rows:
        fieldnames = list(output_rows[0].keys())
        if "body_html" not in fieldnames:
            fieldnames.append("body_html")
        if "tags" not in fieldnames:
            fieldnames.append("tags")
        write_csv(output_csv, output_rows, fieldnames)
        logger.info(f"結果を {output_csv} に出力しました")

    return success, failed
