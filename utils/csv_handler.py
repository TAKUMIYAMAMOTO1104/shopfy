import csv
from pathlib import Path


def read_csv(path: str | Path) -> list[dict]:
    path = Path(path)
    for enc in ("utf-8-sig", "utf-8"):
        try:
            with open(path, encoding=enc) as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    with open(path, encoding="cp932") as f:
        return list(csv.DictReader(f))


def write_csv(path: str | Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ------------------------------------------------------------------ #
# バリデーション
# ------------------------------------------------------------------ #

def _check_required(rows: list[dict], required: set[str], label: str) -> list[str]:
    errors: list[str] = []
    if not rows:
        return [f"{label}: CSVにデータがありません"]
    headers = set(rows[0].keys())
    missing = required - headers
    if missing:
        errors.append(f"{label}: 必須列が不足しています: {', '.join(sorted(missing))}")
    return errors


def validate_create_rows(rows: list[dict]) -> list[str]:
    errors = _check_required(rows, {"title", "price"}, "create")
    for i, row in enumerate(rows, start=2):
        if not row.get("title"):
            errors.append(f"行{i}: titleが空です")
        if not row.get("price"):
            errors.append(f"行{i}: priceが空です")
        else:
            try:
                float(row["price"])
            except ValueError:
                errors.append(f"行{i}: priceが数値ではありません ({row['price']})")
    return errors


def validate_variant_rows(rows: list[dict]) -> list[str]:
    errors = _check_required(rows, {"title", "price"}, "create --variants")
    for i, row in enumerate(rows, start=2):
        if not row.get("title"):
            errors.append(f"行{i}: titleが空です")
        if not row.get("price"):
            errors.append(f"行{i}: priceが空です")
    return errors


def validate_update_rows(rows: list[dict]) -> list[str]:
    errors: list[str] = []
    if not rows:
        return ["update: CSVにデータがありません"]
    for i, row in enumerate(rows, start=2):
        if not row.get("product_id") and not row.get("sku"):
            errors.append(f"行{i}: product_idまたはskuが必要です")
    return errors


def validate_delete_rows(rows: list[dict]) -> list[str]:
    errors: list[str] = []
    if not rows:
        return ["delete: CSVにデータがありません"]
    for i, row in enumerate(rows, start=2):
        if not row.get("product_id") and not row.get("sku"):
            errors.append(f"行{i}: product_idまたはskuが必要です")
        mode = row.get("mode", "archive")
        if mode not in ("archive", "delete"):
            errors.append(f"行{i}: modeは 'archive' または 'delete' を指定してください ({mode})")
    return errors


def validate_sync_inventory_rows(rows: list[dict]) -> list[str]:
    errors = _check_required(rows, {"sku", "inventory_quantity"}, "sync-inventory")
    for i, row in enumerate(rows, start=2):
        if not row.get("sku"):
            errors.append(f"行{i}: skuが空です")
        qty = row.get("inventory_quantity", "")
        if qty != "":
            try:
                int(qty)
            except ValueError:
                errors.append(f"行{i}: inventory_quantityが整数ではありません ({qty})")
    return errors


# ------------------------------------------------------------------ #
# 変換
# ------------------------------------------------------------------ #

def group_by_product(rows: list[dict]) -> list[list[dict]]:
    """title連続同名行を1商品グループに束ねる"""
    groups: list[list[dict]] = []
    for row in rows:
        title = row.get("title", "")
        if groups and groups[-1][0].get("title") == title:
            groups[-1].append(row)
        else:
            groups.append([row])
    return groups


def parse_product_row(row: dict) -> dict:
    """単一バリアント行をShopify商品ペイロードに変換"""
    variant: dict = {
        "price": row["price"],
        "inventory_management": "shopify",
        "inventory_policy": row.get("inventory_policy") or "deny",
    }
    _copy_if(row, variant, "compare_at_price")
    _copy_if(row, variant, "sku")
    _copy_if(row, variant, "barcode")
    if row.get("inventory_quantity"):
        variant["inventory_quantity"] = int(row["inventory_quantity"])
    if row.get("weight"):
        variant["weight"] = float(row["weight"])
        variant["weight_unit"] = row.get("weight_unit") or "kg"

    # option1 (単一バリアント用)
    if row.get("option1_name") and row.get("option1_value"):
        variant["option1"] = row["option1_value"]

    product: dict = {
        "title": row["title"],
        "variants": [variant],
        "status": row.get("status") or "active",
        "published": True,
    }
    _copy_if(row, product, "body_html")
    _copy_if(row, product, "vendor")
    _copy_if(row, product, "product_type")
    _copy_if(row, product, "tags")

    if row.get("option1_name") and row.get("option1_value"):
        product["options"] = [{"name": row["option1_name"], "values": [row["option1_value"]]}]

    return product


def parse_variant_group(rows: list[dict]) -> dict:
    """複数バリアント行グループをShopify商品ペイロードに変換"""
    first = rows[0]
    option_names: list[str] = []
    for i in (1, 2, 3):
        name = first.get(f"option{i}_name", "")
        if name:
            option_names.append(name)

    variants: list[dict] = []
    images: list[dict] = []
    seen_urls: set[str] = set()

    for row in rows:
        v: dict = {
            "price": row["price"],
            "inventory_management": "shopify",
            "inventory_policy": row.get("inventory_policy") or "deny",
        }
        _copy_if(row, v, "compare_at_price")
        _copy_if(row, v, "sku")
        _copy_if(row, v, "barcode")
        if row.get("inventory_quantity"):
            v["inventory_quantity"] = int(row["inventory_quantity"])
        if row.get("weight"):
            v["weight"] = float(row["weight"])
            v["weight_unit"] = row.get("weight_unit") or "kg"
        for i in (1, 2, 3):
            val = row.get(f"option{i}_value", "")
            if val:
                v[f"option{i}"] = val
        variants.append(v)

        url = row.get("image_url", "")
        if url and url not in seen_urls:
            img: dict = {"src": url}
            if row.get("image_alt_text"):
                img["alt"] = row["image_alt_text"]
            if row.get("image_position"):
                img["position"] = int(row["image_position"])
            images.append(img)
            seen_urls.add(url)

    product: dict = {
        "title": first["title"],
        "variants": variants,
        "status": first.get("status") or "active",
        "published": True,
    }
    _copy_if(first, product, "body_html")
    _copy_if(first, product, "vendor")
    _copy_if(first, product, "product_type")
    _copy_if(first, product, "tags")
    if option_names:
        product["options"] = [{"name": n} for n in option_names]

    return product, images


def parse_update_row(row: dict) -> tuple[str | None, int | None, dict, dict]:
    """(sku, product_id, product_payload, variant_payload)を返す"""
    sku = row.get("sku") or None
    product_id: int | None = None
    if row.get("product_id"):
        try:
            product_id = int(row["product_id"])
        except ValueError:
            pass

    product_payload: dict = {}
    for field in ("title", "body_html", "vendor", "product_type", "tags", "status"):
        if row.get(field):
            product_payload[field] = row[field]

    variant_payload: dict = {}
    for field in ("price", "compare_at_price", "sku", "barcode"):
        if row.get(field):
            variant_payload[field] = row[field]
    if row.get("inventory_quantity") and row["inventory_quantity"] != "":
        variant_payload["inventory_quantity"] = int(row["inventory_quantity"])

    return sku, product_id, product_payload, variant_payload


def _copy_if(src: dict, dst: dict, key: str) -> None:
    val = src.get(key, "")
    if val:
        dst[key] = val
