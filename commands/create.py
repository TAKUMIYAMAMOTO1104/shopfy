import json
import sys

import requests

from shopify_client import ShopifyClient
from utils.csv_handler import (
    read_csv,
    validate_create_rows,
    validate_variant_rows,
    parse_product_row,
    parse_variant_group,
    group_by_product,
    write_csv,
)
from utils.logger import setup_logger

logger = setup_logger(__name__)


def run_create(
    csv_path: str,
    client: ShopifyClient,
    dry_run: bool = False,
    use_variants: bool = False,
    output_errors: str | None = None,
) -> tuple[int, int]:
    rows = read_csv(csv_path)

    errors = validate_variant_rows(rows) if use_variants else validate_create_rows(rows)
    if errors:
        for e in errors:
            logger.error(e)
        sys.exit(1)

    if use_variants:
        groups = group_by_product(rows)
        total = len(groups)
        logger.info(f"{total}件の商品（バリアント込み）を処理します (dry_run={dry_run})")
        success, failed = 0, 0
        failed_rows: list[dict] = []

        for i, group in enumerate(groups, start=1):
            title = group[0].get("title", "")
            try:
                product_data, images = parse_variant_group(group)
                if dry_run:
                    logger.info(f"[DRY-RUN] 商品{i}/{total}: {json.dumps(product_data, ensure_ascii=False)}")
                    success += 1
                    continue
                created = client.create_product(product_data)
                product_id = created["id"]
                logger.info(f"[{i}/{total}] 登録成功: {title} (ID: {product_id}, バリアント数: {len(group)})")
                for img in images:
                    try:
                        client.upload_image(product_id, img["src"], img.get("alt", ""), img.get("position", 1))
                    except requests.HTTPError as e:
                        logger.warning(f"  画像アップロード失敗: {e}")
                success += 1
            except Exception as e:
                logger.error(f"[{i}/{total}] 登録失敗: {title} - {e}")
                for row in group:
                    failed_rows.append(row)
                failed += 1

    else:
        total = len(rows)
        logger.info(f"{total}件の商品を処理します (dry_run={dry_run})")
        success, failed = 0, 0
        failed_rows = []

        for i, row in enumerate(rows, start=1):
            title = row.get("title", "")
            try:
                product_data = parse_product_row(row)
                if dry_run:
                    logger.info(f"[DRY-RUN] 商品{i}/{total}: {json.dumps(product_data, ensure_ascii=False)}")
                    success += 1
                    continue
                created = client.create_product(product_data)
                product_id = created["id"]
                logger.info(f"[{i}/{total}] 登録成功: {title} (ID: {product_id})")
                if row.get("image_url"):
                    try:
                        client.upload_image(
                            product_id,
                            row["image_url"],
                            row.get("image_alt_text", ""),
                            1,
                        )
                        logger.info(f"  画像アップロード完了")
                    except requests.HTTPError as e:
                        logger.warning(f"  画像アップロード失敗: {e}")
                success += 1
            except Exception as e:
                logger.error(f"[{i}/{total}] 登録失敗: {title} - {e}")
                failed_rows.append(row)
                failed += 1

    logger.info(f"完了: 成功={success}件, 失敗={failed}件")
    if output_errors and failed_rows:
        write_csv(output_errors, failed_rows, list(failed_rows[0].keys()))
        logger.info(f"失敗行を {output_errors} に出力しました")

    return success, failed
