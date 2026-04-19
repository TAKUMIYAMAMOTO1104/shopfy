"""Claude API wrapper — 商品説明・タグ・価格提案の自動生成"""
import json

import anthropic

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def generate_product_description(
    title: str,
    product_type: str = "",
    vendor: str = "",
    tags: str = "",
    price: str = "",
) -> str:
    """SEO最適化された日本語商品説明文(body_html)を生成する"""
    prompt = f"""以下のShopify商品情報を基に、SEO最適化された魅力的な日本語の商品説明文(body_html)を生成してください。

商品名: {title}
商品タイプ: {product_type or "未指定"}
ブランド: {vendor or "未指定"}
タグ: {tags or "未指定"}
価格: {price or "未指定"}

要件:
- <p>, <ul>, <li>, <strong> などのHTMLタグを使用してフォーマットする
- 購買意欲を高める説得力のある文章
- SEOキーワードを自然に含める
- 特徴・メリット・使用シーンを含める
- 商品説明のHTMLのみを出力（前置き・説明不要）"""

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system="あなたはShopifyの商品ページを最適化するプロのコピーライターです。",
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def generate_seo_tags(
    title: str,
    product_type: str = "",
    vendor: str = "",
    existing_tags: str = "",
) -> str:
    """SEO最適化されたタグをカンマ区切りで生成する"""
    prompt = f"""以下のShopify商品情報を基に、検索最適化されたタグを10〜15個生成してください。

商品名: {title}
商品タイプ: {product_type or "未指定"}
ブランド: {vendor or "未指定"}
既存タグ: {existing_tags or "なし"}

要件:
- カンマ区切りで出力（タグのみ、前置き・番号不要）
- 日本語と英語を混在させてよい
- 検索ボリュームが高いキーワードを優先"""

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def suggest_price(
    title: str,
    product_type: str = "",
    vendor: str = "",
    current_price: str = "",
    inventory_quantity: int = 0,
) -> dict:
    """価格提案をJSON形式で返す"""
    prompt = f"""以下のShopify商品情報を基に、最適な価格戦略を提案してください。

商品名: {title}
商品タイプ: {product_type or "未指定"}
ブランド: {vendor or "未指定"}
現在価格: {current_price or "未設定"}
在庫数: {inventory_quantity}

以下のJSONのみで回答（説明不要）:
{{
  "recommended_price": 数値,
  "compare_at_price": 数値,
  "reason": "理由を一文で"
}}"""

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()
    # JSONブロック抽出
    if "```" in text:
        text = text.split("```")[1].lstrip("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def generate_inventory_summary(products: list[dict]) -> str:
    """在庫データからAIサマリーを生成する"""
    total = len(products)
    low_stock = [p for p in products if p.get("total_inventory", 999) <= 5]
    out_of_stock = [p for p in products if p.get("total_inventory", 1) == 0]

    snapshot = json.dumps(
        [
            {
                "title": p.get("title"),
                "inventory": p.get("total_inventory"),
                "status": p.get("status"),
                "vendor": p.get("vendor"),
            }
            for p in products[:50]  # 先頭50件でサマリー生成
        ],
        ensure_ascii=False,
    )

    prompt = f"""Shopifyストアの在庫状況を分析し、オーナーへの日本語レポートサマリーを生成してください。

総商品数: {total}件
在庫切れ: {len(out_of_stock)}件
残り5個以下: {len(low_stock)}件

商品データ(抜粋):
{snapshot}

要件:
- 現状の課題と改善提案を3点
- 今すぐ対応すべきアクション
- 300文字以内"""

    message = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()
