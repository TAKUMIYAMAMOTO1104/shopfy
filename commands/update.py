import sys

from shopify_client import ShopifyClient
from utils.csv_handler import read_csv, validate_update_rows, parse_update_row, write_csv
from utils.logger import setup_logger

logger = setup_logger(__name__)


def run_update(
    csv_path: str,
    client: ShopifyClient,
    dry_run: bool = False,
    field: str | None = None,
    output_errors: str | None = None,
) -> tuple[int, int]:
    rows = read_csv(csv_path)
    errors = validate_update_rows(rows)
    if errors:
        for e in errors:
            logger.error(e)
        sys.exit(1)

    total = len(rows)
    logger.info(f"{total}件の商品を更新します (dry_run={dry_run})")
    success, failed = 0, 0
    failed_rows: list[dict] = []

    for i, row in enumerate(rows, start=1):
        sku, product_id, product_payload, variant_payload = parse_update_row(row)

        if field:
            product_payload = {k: v for k, v in product_payload.items() if k == field}
            variant_payload = {k: v for k, v in variant_payload.items() if k == field}

        label = sku or str(product_id)
        try:
            resolved_product_id, resolved_variant_id = _resolve(client, sku, product_id)
            if resolved_product_id is None:
                logger.error(f"[{i}/{total}] 商品が見つかりません: {label}")
                failed_rows.append(row)
                failed += 1
                continue

            if dry_run:
                logger.info(
                    f"[DRY-RUN] {i}/{total} {label}: product={product_payload}, variant={variant_payload}"
                )
                success += 1
                continue

            if product_payload:
                client.update_product(resolved_product_id, product_payload)
            if variant_payload and resolved_variant_id:
                client.update_variant(resolved_variant_id, variant_payload)

            logger.info(f"[{i}/{total}] 更新成功: {label} (ID: {resolved_product_id})")
            success += 1
        except Exception as e:
            logger.error(f"[{i}/{total}] 更新失敗: {label} - {e}")
            failed_rows.append(row)
            failed += 1

    logger.info(f"完了: 成功={success}件, 失敗={failed}件")
    if output_errors and failed_rows:
        write_csv(output_errors, failed_rows, list(failed_rows[0].keys()))
        logger.info(f"失敗行を {output_errors} に出力しました")

    return success, failed


def _resolve(client: ShopifyClient, sku: str | None, product_id: int | None) -> tuple[int | None, int | None]:
    if product_id:
        product = client.get_product_by_id(product_id)
        if product:
            variant_id = product.get("variants", [{}])[0].get("id") if product.get("variants") else None
            return product_id, variant_id
        return None, None
    if sku:
        product, variant = client.find_product_by_sku(sku)
        if product and variant:
            return product["id"], variant["id"]
    return None, None
