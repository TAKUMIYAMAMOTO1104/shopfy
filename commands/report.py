"""在庫・売上レポート自動生成コマンド

使い方:
  python shopify_manager.py report --output report.csv [--ai-summary] [--low-stock N]
"""
import csv
import os
from datetime import datetime
from pathlib import Path

from shopify_client import ShopifyClient
from utils.logger import setup_logger

logger = setup_logger(__name__)

REPORT_FIELDNAMES = [
    "product_id", "title", "vendor", "product_type", "status",
    "total_inventory", "variant_count", "price_min", "price_max",
    "has_sku", "tags", "created_at", "updated_at", "alert",
]


def run_report(
    output_path: str,
    client: ShopifyClient,
    ai_summary: bool = False,
    low_stock_threshold: int = 5,
    status: str = "any",
) -> int:
    logger.info("商品データを取得しています...")
    params: dict = {}
    if status != "any":
        params["status"] = status
    products = client.get_all_products(params)
    if not products:
        logger.warning("商品が見つかりませんでした")
        return 0

    logger.info(f"{len(products)}件の商品を取得しました。在庫情報を取得中...")
    inventory_map = _build_inventory_map(client, products)

    rows: list[dict] = []
    for product in products:
        row = _summarize_product(product, inventory_map, low_stock_threshold)
        rows.append(row)

    # アラート順にソート（在庫切れ→低在庫→正常）
    rows.sort(key=lambda r: (0 if r["alert"] == "在庫切れ" else 1 if r["alert"] == "低在庫" else 2))

    _write_report(output_path, rows)
    logger.info(f"レポートを {output_path} に出力しました ({len(rows)}件)")

    _print_summary(rows, low_stock_threshold)

    if ai_summary:
        _generate_ai_summary(products, inventory_map, output_path)

    return len(rows)


def _summarize_product(product: dict, inventory_map: dict[int, int], low_stock: int) -> dict:
    variants = product.get("variants", [])
    prices = [float(v.get("price", 0) or 0) for v in variants]
    total_inv = sum(
        inventory_map.get(v.get("inventory_item_id", 0), 0) for v in variants
    )
    has_sku = any(v.get("sku") for v in variants)

    if total_inv == 0:
        alert = "在庫切れ"
    elif total_inv <= low_stock:
        alert = "低在庫"
    else:
        alert = ""

    return {
        "product_id": product.get("id", ""),
        "title": product.get("title", ""),
        "vendor": product.get("vendor", ""),
        "product_type": product.get("product_type", ""),
        "status": product.get("status", ""),
        "total_inventory": total_inv,
        "variant_count": len(variants),
        "price_min": min(prices) if prices else "",
        "price_max": max(prices) if prices else "",
        "has_sku": "yes" if has_sku else "no",
        "tags": product.get("tags", ""),
        "created_at": product.get("created_at", ""),
        "updated_at": product.get("updated_at", ""),
        "alert": alert,
    }


def _write_report(output_path: str, rows: list[dict]) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _print_summary(rows: list[dict], low_stock: int) -> None:
    total = len(rows)
    out_of_stock = [r for r in rows if r["alert"] == "在庫切れ"]
    low = [r for r in rows if r["alert"] == "低在庫"]
    active = [r for r in rows if r.get("status") == "active"]

    logger.info("=" * 50)
    logger.info(f"[レポートサマリー] {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info(f"  総商品数   : {total}件")
    logger.info(f"  公開中     : {len(active)}件")
    logger.info(f"  在庫切れ   : {len(out_of_stock)}件")
    logger.info(f"  低在庫(≤{low_stock}): {len(low)}件")
    if out_of_stock:
        logger.warning("【要対応】在庫切れ商品:")
        for r in out_of_stock[:10]:
            logger.warning(f"  - {r['title']} (ID: {r['product_id']})")
    if low:
        logger.warning(f"【注意】低在庫商品({len(low)}件):")
        for r in low[:5]:
            logger.warning(f"  - {r['title']} 残{r['total_inventory']}個")
    logger.info("=" * 50)


def _generate_ai_summary(products: list[dict], inventory_map: dict[int, int], output_path: str) -> None:
    try:
        from utils.ai_client import generate_inventory_summary

        enriched = []
        for p in products:
            variants = p.get("variants", [])
            total_inv = sum(inventory_map.get(v.get("inventory_item_id", 0), 0) for v in variants)
            enriched.append({**p, "total_inventory": total_inv})

        logger.info("AIサマリーを生成しています...")
        summary = generate_inventory_summary(enriched)

        summary_path = Path(output_path).with_suffix(".summary.txt")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(f"=== AIレポートサマリー {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n\n")
            f.write(summary)
            f.write("\n")
        logger.info(f"AIサマリーを {summary_path} に出力しました")
        logger.info(f"\n{summary}")
    except Exception as e:
        logger.warning(f"AIサマリーの生成に失敗しました: {e}")


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
