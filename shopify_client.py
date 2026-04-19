import time
import threading
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from utils.logger import setup_logger

logger = setup_logger(__name__)

API_VERSION = "2024-01"


class RateLimiter:
    """トークンバケット方式レート制限: 2 req/秒"""

    def __init__(self, calls_per_second: float = 2.0):
        self._min_interval = 1.0 / calls_per_second
        self._last_called: float = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_called
            remaining = self._min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
            self._last_called = time.monotonic()


def _is_retryable(exc: BaseException) -> bool:
    return (
        isinstance(exc, requests.HTTPError)
        and exc.response is not None
        and exc.response.status_code in (429, 500, 502, 503, 504)
    )


class ShopifyClient:
    def __init__(self, shop_name: str, access_token: str):
        # フルドメイン (xxx.myshopify.com) でも受け付ける
        host = shop_name.replace("https://", "").replace("http://", "").rstrip("/")
        if not host.endswith(".myshopify.com"):
            host = f"{host}.myshopify.com"
        self.base_url = f"https://{host}/admin/api/{API_VERSION}"
        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }
        self._rate_limiter = RateLimiter()
        self._sku_cache: dict[str, tuple[int, int]] = {}  # sku -> (product_id, variant_id)

    # ------------------------------------------------------------------ #
    # 内部ヘルパー
    # ------------------------------------------------------------------ #

    def _raw_request(self, method: str, endpoint: str, payload: dict | None = None, params: dict | None = None) -> requests.Response:
        self._rate_limiter.wait()
        url = f"{self.base_url}/{endpoint}"
        resp = requests.request(method, url, headers=self.headers, json=payload, params=params, timeout=30)

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", 2.0))
            logger.warning(f"レート制限に到達。{retry_after}秒後にリトライします...")
            time.sleep(retry_after)
            resp.raise_for_status()

        if resp.status_code == 422:
            logger.error(f"バリデーションエラー: {resp.text}")
            resp.raise_for_status()

        resp.raise_for_status()
        return resp

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception(_is_retryable),
    )
    def _request(self, method: str, endpoint: str, payload: dict | None = None, params: dict | None = None) -> dict:
        resp = self._raw_request(method, endpoint, payload, params)
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def _paginate(self, endpoint: str, key: str, params: dict | None = None) -> list[dict]:
        results: list[dict] = []
        p = dict(params or {})
        p.setdefault("limit", 250)

        while True:
            self._rate_limiter.wait()
            url = f"{self.base_url}/{endpoint}"
            resp = requests.get(url, headers=self.headers, params=p, timeout=30)
            resp.raise_for_status()
            batch = resp.json().get(key, [])
            results.extend(batch)

            link = resp.headers.get("Link", "")
            next_url = self._parse_next_link(link)
            if not next_url:
                break
            # page_info形式に切り替え
            p = {"limit": 250, "page_info": self._extract_page_info(next_url)}

        return results

    @staticmethod
    def _parse_next_link(link_header: str) -> str | None:
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                return url
        return None

    @staticmethod
    def _extract_page_info(url: str) -> str:
        for part in url.split("?", 1)[-1].split("&"):
            if part.startswith("page_info="):
                return part[len("page_info="):]
        return ""

    # ------------------------------------------------------------------ #
    # 商品 CRUD
    # ------------------------------------------------------------------ #

    def get_all_products(self, params: dict | None = None) -> list[dict]:
        return self._paginate("products.json", "products", params)

    def get_product_by_id(self, product_id: int) -> dict:
        return self._request("GET", f"products/{product_id}.json").get("product", {})

    def find_product_by_sku(self, sku: str) -> tuple[dict | None, dict | None]:
        if sku in self._sku_cache:
            product_id, variant_id = self._sku_cache[sku]
            product = self.get_product_by_id(product_id)
            variant = next((v for v in product.get("variants", []) if v["id"] == variant_id), None)
            if variant:
                return product, variant

        products = self._paginate("products.json", "products", {"fields": "id,variants", "limit": 250})
        for product in products:
            for variant in product.get("variants", []):
                if variant.get("sku") == sku:
                    self._sku_cache[sku] = (product["id"], variant["id"])
                    return product, variant
        return None, None

    def create_product(self, product_data: dict) -> dict:
        return self._request("POST", "products.json", {"product": product_data}).get("product", {})

    def update_product(self, product_id: int, product_data: dict) -> dict:
        return self._request("PUT", f"products/{product_id}.json", {"product": product_data}).get("product", {})

    def delete_product(self, product_id: int) -> None:
        self._request("DELETE", f"products/{product_id}.json")

    def archive_product(self, product_id: int) -> dict:
        return self.update_product(product_id, {"status": "archived"})

    # ------------------------------------------------------------------ #
    # バリアント・画像
    # ------------------------------------------------------------------ #

    def update_variant(self, variant_id: int, variant_data: dict) -> dict:
        return self._request("PUT", f"variants/{variant_id}.json", {"variant": variant_data}).get("variant", {})

    def upload_image(self, product_id: int, image_url: str, alt_text: str = "", position: int = 1) -> dict:
        payload: dict[str, Any] = {"src": image_url, "position": position}
        if alt_text:
            payload["alt"] = alt_text
        return self._request("POST", f"products/{product_id}/images.json", {"image": payload}).get("image", {})

    # ------------------------------------------------------------------ #
    # 在庫
    # ------------------------------------------------------------------ #

    def get_locations(self) -> list[dict]:
        return self._request("GET", "locations.json").get("locations", [])

    def set_inventory_level(self, inventory_item_id: int, location_id: int, quantity: int) -> dict:
        payload = {
            "location_id": location_id,
            "inventory_item_id": inventory_item_id,
            "available": quantity,
        }
        return self._request("POST", "inventory_levels/set.json", payload)

    def get_inventory_levels_batch(self, inventory_item_ids: list[int], location_id: int) -> list[dict]:
        ids_str = ",".join(str(i) for i in inventory_item_ids)
        return self._request(
            "GET", "inventory_levels.json", params={"inventory_item_ids": ids_str, "location_ids": str(location_id)}
        ).get("inventory_levels", [])

    # ------------------------------------------------------------------ #
    # 注文
    # ------------------------------------------------------------------ #

    def get_orders(self, since: str | None = None, status: str = "any") -> list[dict]:
        params: dict = {"status": status, "limit": 250}
        if since:
            params["created_at_min"] = since
        return self._paginate("orders.json", "orders", params)
