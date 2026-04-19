import os
import sys

from shopify_client import ShopifyClient
from utils.csv_handler import read_csv, validate_sync_inventory_rows, write_csv
from utils.logger import setup_logger

logger = setup_logger(__name__)


def run_sync_inventory(
    csv_path: str,
    client: ShopifyClient,
    location_id: int | None = None,
    dry_run: bool = False,
    output_errors: str | None = None,
) -> tuple[int, int]:
    rows = read_csv(csv_path)
    errors = validate_sync_inventory_rows(rows)
    if errors:
        for e in errors:
            logger.error(e)
        sys.exit(1)

    resolved_location_id = location_id or _get_location_id(client)
    if not resolved_location_id:
        logger.error("ロケーションIDが取得できません。--location-idまたは.envのSHOPIFY_LOCATION_IDを設定してください")
        sys.exit(1)

    total = len(rows)
    logger.info(f"{total}件の在庫を同期します (location_id={resolved_location_id}, dry_run={dry_run})")
    success, failed = 0, 0
    failed_rows: list[dict] = []

    for i, row in enumerate(rows, start=1):
        sku = row["sku"]
        quantity = int(row["inventory_quantity"])
        loc_id = int(row.get("location_id") or resolved_location_id)

        try:
            _, variant = client.find_product_by_sku(sku)
            if variant is None:
                logger.error(f"[{i}/{total}] SKUが見つかりません: {sku}")
                failed_rows.append(row)
                failed += 1
                continue

            inventory_item_id = variant["inventory_item_id"]

            if dry_run:
                logger.info(f"[DRY-RUN] {i}/{total} SKU={sku}: 在庫={quantity} (inventory_item_id={inventory_item_id})")
                success += 1
                continue

            client.set_inventory_level(inventory_item_id, loc_id, quantity)
            logger.info(f"[{i}/{total}] 在庫更新成功: SKU={sku}, 数量={quantity}")
            success += 1
        except Exception as e:
            logger.error(f"[{i}/{total}] 在庫更新失敗: SKU={sku} - {e}")
            failed_rows.append(row)
            failed += 1

    logger.info(f"完了: 成功={success}件, 失敗={failed}件")
    if output_errors and failed_rows:
        write_csv(output_errors, failed_rows, list(failed_rows[0].keys()))
        logger.info(f"失敗行を {output_errors} に出力しました")

    return success, failed


def _get_location_id(client: ShopifyClient) -> int | None:
    env_id = os.getenv("SHOPIFY_LOCATION_ID", "").strip()
    if env_id:
        return int(env_id)
    locations = client.get_locations()
    active = [loc for loc in locations if loc.get("active")]
    if active:
        return active[0]["id"]
    return locations[0]["id"] if locations else None
