"""価格自動最適化コマンド

ルールベース + AI提案で価格を自動調整する。

使い方:
  python shopify_manager.py optimize-price [--dry-run] [--ai] [--low-stock N] [--high-stock N]
  python shopify_manager.py optimize-price --dry-run --ai
"""
import time

from shopify_client import ShopifyClient
from utils.logger import setup_logger

logger = setup_logger(__name__)


def run_optimize_price(
    client: ShopifyClient,
    dry_run: bool = False,
    use_ai: bool = False,
    low_stock: int = 5,
    high_stock: int = 50,
    low_stock_markup: float = 0.10,
    high_stock_discount: float = 0.10,
) -> tuple[int, int]:
    """
    在庫状況に応じて価格を自動調整する。

    - 在庫 <= low_stock  → 価格を markup 分値上げ（希少性プレミアム）
    - 在庫 >= high_stock → 価格を discount 分値下げ（回転率改善）
    - AIモード: Claude が個別提案
    """
    logger.info("商品データを取得しています...")
    products = client.get_all_products({"status": "active"})
    if not products:
        logger.warning("アクティブな商品が見つかりませんでした")
        return 0, 0

    inventory_map = _build_inventory_map(client, products)
    logger.info(f"{len(products)}件の商品を価格最適化します (dry_run={dry_run})")

    success, failed = 0, 0

    for i, product in enumerate(products, start=1):
        title = product.get("title", "")
        product_id = product["id"]
        variants = product.get("variants", [])

        total_inv = sum(
            inventory_map.get(v.get("inventory_item_id", 0), 0) for v in variants
        )

        try:
            if use_ai:
                updated = _ai_optimize(client, product, total_inv, dry_run)
            else:
                updated = _rule_optimize(
                    client, product, total_inv, dry_run,
                    low_stock, high_stock, low_stock_markup, high_stock_discount,
                )

            if updated:
                logger.info(f"[{i}/{len(products)}] 最適化: {title} (在庫={total_inv})")
                success += 1
            else:
                success += 1  # 変更なしも正常
        except Exception as e:
            logger.error(f"[{i}/{len(products)}] 失敗: {title} - {e}")
            failed += 1

        if i < len(products):
            time.sleep(0.3)

    logger.info(f"完了: 処理={success}件, 失敗={failed}件")
    return success, failed


def _rule_optimize(
    client: ShopifyClient,
    product: dict,
    total_inv: int,
    dry_run: bool,
    low_stock: int,
    high_stock: int,
    markup: float,
    discount: float,
) -> bool:
    title = product.get("title", "")
    variants = product.get("variants", [])
    changed = False

    for variant in variants:
        current_price = float(variant.get("price", 0) or 0)
        if current_price <= 0:
            continue

        new_price: float | None = None
        reason = ""

        if total_inv <= low_stock and total_inv > 0:
            new_price = round(current_price * (1 + markup), 0)
            reason = f"低在庫({total_inv}個) → {markup*100:.0f}%値上げ"
        elif total_inv >= high_stock:
            new_price = round(current_price * (1 - discount), 0)
            reason = f"高在庫({total_inv}個) → {discount*100:.0f}%値下げ"

        if new_price and new_price != current_price:
            if dry_run:
                logger.info(
                    f"  [DRY-RUN] {title} / バリアント{variant['id']}: "
                    f"¥{current_price:.0f} → ¥{new_price:.0f} ({reason})"
                )
            else:
                client.update_variant(
                    variant["id"],
                    {
                        "price": str(new_price),
                        "compare_at_price": str(current_price),
                    },
                )
                logger.info(
                    f"  {title} / バリアント{variant['id']}: "
                    f"¥{current_price:.0f} → ¥{new_price:.0f} ({reason})"
                )
            changed = True

    return changed


def _ai_optimize(
    client: ShopifyClient,
    product: dict,
    total_inv: int,
    dry_run: bool,
) -> bool:
    from utils.ai_client import suggest_price

    title = product.get("title", "")
    variants = product.get("variants", [])
    if not variants:
        return False

    variant = variants[0]
    current_price = variant.get("price", "")

    suggestion = suggest_price(
        title=title,
        product_type=product.get("product_type", ""),
        vendor=product.get("vendor", ""),
        current_price=current_price,
        inventory_quantity=total_inv,
    )

    if not suggestion or "recommended_price" not in suggestion:
        return False

    new_price = suggestion["recommended_price"]
    compare_at = suggestion.get("compare_at_price", "")
    reason = suggestion.get("reason", "")

    if float(new_price) == float(current_price or 0):
        return False

    if dry_run:
        logger.info(
            f"  [DRY-RUN][AI] {title}: ¥{current_price} → ¥{new_price} | {reason}"
        )
    else:
        update: dict = {"price": str(new_price)}
        if compare_at:
            update["compare_at_price"] = str(compare_at)
        client.update_variant(variant["id"], update)
        logger.info(f"  [AI] {title}: ¥{current_price} → ¥{new_price} | {reason}")

    return True


def _build_inventory_map(client: ShopifyClient, products: list[dict]) -> dict[int, int]:
    locations = client.get_locations()
    if not locations:
        return {}
    location_id = next((loc["id"] for loc in locations if loc.get("active")), locations[0]["id"])

    all_item_ids = [
        v["inventory_item_id"]
        for p in products
        for v in p.get("variants", [])
        if v.get("inventory_item_id")
    ]

    result: dict[int, int] = {}
    for i in range(0, len(all_item_ids), 50):
        batch = all_item_ids[i:i + 50]
        try:
            levels = client.get_inventory_levels_batch(batch, location_id)
            for level in levels:
                result[level["inventory_item_id"]] = level.get("available", 0)
        except Exception as e:
            logger.warning(f"在庫数取得に一部失敗: {e}")

    return result
