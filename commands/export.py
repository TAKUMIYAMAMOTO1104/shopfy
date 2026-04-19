import sys

from shopify_client import ShopifyClient
from utils.csv_handler import write_csv
from utils.logger import setup_logger

logger = setup_logger(__name__)

EXPORT_FIELDNAMES = [
    "product_id", "variant_id", "title", "body_html", "vendor",
    "product_type", "tags", "status",
    "option1_name", "option1_value", "option2_name", "option2_value", "option3_name", "option3_value",
    "price", "compare_at_price", "sku", "barcode",
    "inventory_quantity", "weight", "weight_unit",
    "image_url", "created_at", "updated_at",
]


def run_export(
    output_path: str,
    client: ShopifyClient,
    status: str = "any",
    product_type: str | None = None,
    vendor: str | None = None,
    limit: int | None = None,
) -> int:
    params: dict = {}
    if status != "any":
        params["status"] = status
    if product_type:
        params["product_type"] = product_type
    if vendor:
        params["vendor"] = vendor

    logger.info("商品データを取得しています...")
    products = client.get_all_products(params)

    if limit:
        products = products[:limit]

    logger.info(f"{len(products)}件の商品を取得しました。在庫数を取得しています...")

    # 在庫数をバッチ取得
    inventory_map = _build_inventory_map(client, products)

    rows: list[dict] = []
    for product in products:
        rows.extend(_product_to_rows(product, inventory_map))

    if not rows:
        logger.warning("エクスポートするデータがありません")
        return 0

    write_csv(output_path, rows, EXPORT_FIELDNAMES)
    logger.info(f"{len(rows)}行を {output_path} に出力しました")
    return len(rows)


def _product_to_rows(product: dict, inventory_map: dict[int, int]) -> list[dict]:
    title = product.get("title", "")
    body_html = product.get("body_html", "")
    vendor = product.get("vendor", "")
    product_type = product.get("product_type", "")
    tags = product.get("tags", "")
    status = product.get("status", "")
    created_at = product.get("created_at", "")
    updated_at = product.get("updated_at", "")
    image_url = product.get("image", {}).get("src", "") if product.get("image") else ""

    options = product.get("options", [])
    option_names = [o.get("name", "") for o in options]

    variants = product.get("variants", [])
    result: list[dict] = []
    for variant in variants:
        opt_values = [variant.get(f"option{i+1}", "") for i in range(3)]
        row = {
            "product_id": product["id"],
            "variant_id": variant["id"],
            "title": title,
            "body_html": body_html,
            "vendor": vendor,
            "product_type": product_type,
            "tags": tags,
            "status": status,
            "option1_name": option_names[0] if len(option_names) > 0 else "",
            "option1_value": opt_values[0],
            "option2_name": option_names[1] if len(option_names) > 1 else "",
            "option2_value": opt_values[1],
            "option3_name": option_names[2] if len(option_names) > 2 else "",
            "option3_value": opt_values[2],
            "price": variant.get("price", ""),
            "compare_at_price": variant.get("compare_at_price", ""),
            "sku": variant.get("sku", ""),
            "barcode": variant.get("barcode", ""),
            "inventory_quantity": inventory_map.get(variant.get("inventory_item_id"), ""),
            "weight": variant.get("weight", ""),
            "weight_unit": variant.get("weight_unit", ""),
            "image_url": image_url,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        result.append(row)

    return result


def _build_inventory_map(client: ShopifyClient, products: list[dict]) -> dict[int, int]:
    """inventory_item_id -> available_quantity のマップを構築"""
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
    batch_size = 50
    for i in range(0, len(all_item_ids), batch_size):
        batch = all_item_ids[i:i + batch_size]
        try:
            levels = client.get_inventory_levels_batch(batch, location_id)
            for level in levels:
                result[level["inventory_item_id"]] = level.get("available", 0)
        except Exception as e:
            logger.warning(f"在庫数の取得に一部失敗しました: {e}")

    return result
