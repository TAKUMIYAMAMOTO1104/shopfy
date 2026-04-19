import sys

from shopify_client import ShopifyClient
from utils.csv_handler import read_csv, validate_delete_rows, write_csv
from utils.logger import setup_logger

logger = setup_logger(__name__)


def run_delete(
    csv_path: str,
    client: ShopifyClient,
    dry_run: bool = False,
    force: bool = False,
    output_errors: str | None = None,
) -> tuple[int, int]:
    rows = read_csv(csv_path)
    errors = validate_delete_rows(rows)
    if errors:
        for e in errors:
            logger.error(e)
        sys.exit(1)

    total = len(rows)
    if not dry_run and not force:
        if not _confirm(total):
            logger.info("キャンセルしました")
            return 0, 0

    logger.info(f"{total}件の商品を処理します (dry_run={dry_run})")
    success, failed = 0, 0
    failed_rows: list[dict] = []

    for i, row in enumerate(rows, start=1):
        sku = row.get("sku") or None
        product_id: int | None = None
        if row.get("product_id"):
            try:
                product_id = int(row["product_id"])
            except ValueError:
                pass
        mode = row.get("mode", "archive") or "archive"
        label = sku or str(product_id)

        try:
            resolved_id = _resolve(client, sku, product_id)
            if resolved_id is None:
                logger.error(f"[{i}/{total}] 商品が見つかりません: {label}")
                failed_rows.append(row)
                failed += 1
                continue

            action = "削除" if mode == "delete" else "アーカイブ"
            if dry_run:
                logger.info(f"[DRY-RUN] {i}/{total} {label}: {action}予定 (ID: {resolved_id})")
                success += 1
                continue

            if mode == "delete":
                client.delete_product(resolved_id)
            else:
                client.archive_product(resolved_id)

            logger.info(f"[{i}/{total}] {action}成功: {label} (ID: {resolved_id})")
            success += 1
        except Exception as e:
            logger.error(f"[{i}/{total}] 処理失敗: {label} - {e}")
            failed_rows.append(row)
            failed += 1

    logger.info(f"完了: 成功={success}件, 失敗={failed}件")
    if output_errors and failed_rows:
        write_csv(output_errors, failed_rows, list(failed_rows[0].keys()))
        logger.info(f"失敗行を {output_errors} に出力しました")

    return success, failed


def _confirm(count: int) -> bool:
    answer = input(f"{count}件の商品を操作します。続けますか？ (yes/no): ").strip().lower()
    return answer in ("yes", "y")


def _resolve(client: ShopifyClient, sku: str | None, product_id: int | None) -> int | None:
    if product_id:
        product = client.get_product_by_id(product_id)
        return product.get("id") if product else None
    if sku:
        product, _ = client.find_product_by_sku(sku)
        return product["id"] if product else None
    return None
