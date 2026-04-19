"""AIデジタル商品自動生成コマンド

Claudeがプロンプト集・テンプレート・ノウハウ集を自動生成し
Shopifyに商品として登録する。

使い方:
  python shopify_manager.py gen-product --theme "ChatGPT 副業" --type prompt_pack
  python shopify_manager.py gen-product --theme "マーケティング" --type template
  python shopify_manager.py gen-product --batch 5  # 5商品まとめて生成
  python shopify_manager.py gen-product --batch 5 --dry-run
"""

import json
import time
from dataclasses import dataclass

from shopify_client import ShopifyClient
from utils.logger import setup_logger

logger = setup_logger(__name__)

PRODUCT_TYPES = {
    "prompt_pack": {
        "label": "AIプロンプト集",
        "price_range": (1980, 3980),
        "tags_base": "プロンプト,ChatGPT,AI活用,副業,自動化",
    },
    "template": {
        "label": "ビジネステンプレート",
        "price_range": (4980, 9800),
        "tags_base": "テンプレート,ビジネス,効率化,AI,資料作成",
    },
    "guide": {
        "label": "実践ガイド",
        "price_range": (2980, 5980),
        "tags_base": "ガイド,ノウハウ,副業,収益化,初心者向け",
    },
}

DAILY_THEMES = [
    "ChatGPT副業プロンプト集",
    "SNSマーケティング自動化",
    "Shopify商品説明文テンプレート",
    "YouTube台本生成プロンプト",
    "ブログ記事量産テンプレート",
    "営業メール自動生成プロンプト",
    "ECサイト商品キャッチコピー集",
    "Instagram投稿文テンプレート",
    "リサーチ効率化プロンプト集",
    "プレゼン資料構成テンプレート",
]


@dataclass
class GeneratedProduct:
    title: str
    body_html: str
    price: str
    compare_at_price: str
    tags: str
    product_type: str
    vendor: str
    content_text: str  # 実際の商品コンテンツ（デジタルデータ本体）


def run_gen_product(
    client: ShopifyClient | None,
    theme: str | None = None,
    product_type: str = "prompt_pack",
    batch: int = 1,
    dry_run: bool = False,
    price: int | None = None,
) -> tuple[int, int]:
    if product_type not in PRODUCT_TYPES:
        logger.error(f"無効な商品タイプ: {product_type}. 使用可能: {list(PRODUCT_TYPES.keys())}")
        return 0, 1

    themes = _select_themes(theme, batch)
    logger.info(f"{len(themes)}商品の生成を開始します (type={product_type}, dry_run={dry_run})")

    success, failed = 0, 0

    for i, t in enumerate(themes, start=1):
        logger.info(f"[{i}/{len(themes)}] 生成中: 「{t}」")
        try:
            product = _generate_product(t, product_type, price)
            logger.info(f"  タイトル: {product.title}")
            logger.info(f"  価格: ¥{product.price}")

            if dry_run:
                logger.info(f"  [DRY-RUN] 商品説明(先頭): {product.body_html[:100]}...")
                logger.info(f"  [DRY-RUN] コンテンツ(先頭): {product.content_text[:100]}...")
                success += 1
                continue

            if client:
                shopify_data = _build_shopify_payload(product)
                created = client.create_product(shopify_data)
                product_id = created.get("id")
                logger.info(f"  Shopify登録完了 (ID: {product_id})")

            success += 1

        except Exception as e:
            logger.error(f"[{i}/{len(themes)}] 失敗: {t} - {e}")
            failed += 1

        if i < len(themes):
            time.sleep(1.0)

    logger.info(f"完了: 成功={success}件, 失敗={failed}件")
    return success, failed


def _select_themes(theme: str | None, batch: int) -> list[str]:
    if theme:
        return [theme] * batch if batch > 1 else [theme]
    # バッチ生成時はDAILY_THEMESから循環選択
    import datetime
    offset = datetime.date.today().toordinal() % len(DAILY_THEMES)
    selected = []
    for i in range(batch):
        selected.append(DAILY_THEMES[(offset + i) % len(DAILY_THEMES)])
    return selected


def _generate_product(theme: str, product_type: str, fixed_price: int | None) -> GeneratedProduct:
    from utils.ai_client import _get_client

    client = _get_client()
    type_info = PRODUCT_TYPES[product_type]

    # ① 商品メタ情報を生成
    meta_prompt = f"""以下のテーマでShopifyで販売するデジタル商品のメタ情報をJSONで生成してください。

テーマ: {theme}
商品タイプ: {type_info['label']}

以下のJSON形式のみで出力（説明不要）:
{{
  "title": "商品タイトル（30文字以内、購買意欲を高める）",
  "price": 数値（{type_info['price_range'][0]}〜{type_info['price_range'][1]}の範囲）,
  "compare_at_price": 数値（priceの1.3〜2倍）,
  "tags": "カンマ区切りタグ10個",
  "hook": "購入理由を一文で（50文字以内）"
}}"""

    meta_resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": meta_prompt}],
    )
    meta_text = meta_resp.content[0].text.strip()
    if "```" in meta_text:
        meta_text = meta_text.split("```")[1].lstrip("json").strip()
    meta = json.loads(meta_text)

    # ② 商品コンテンツ本体を生成（実際のプロンプト集・テンプレート）
    content_prompt = _build_content_prompt(theme, product_type)
    content_resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": content_prompt}],
    )
    content_text = content_resp.content[0].text.strip()

    # ③ 商品説明HTML（販売ページ用）
    desc_prompt = f"""以下の商品情報から、Shopify販売ページ用の商品説明HTML(body_html)を生成してください。

商品名: {meta['title']}
フック: {meta['hook']}
商品タイプ: {type_info['label']}
コンテンツ概要: {content_text[:500]}

要件:
- <h2>,<p>,<ul>,<li>,<strong>を使う
- 「こんな人におすすめ」「得られる成果」「内容一覧」セクションを含める
- 購買意欲を高める文章
- HTMLのみ出力"""

    desc_resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": desc_prompt}],
    )

    actual_price = str(fixed_price) if fixed_price else str(meta["price"])
    tags = f"{meta['tags']},{type_info['tags_base']}"

    return GeneratedProduct(
        title=meta["title"],
        body_html=desc_resp.content[0].text.strip(),
        price=actual_price,
        compare_at_price=str(meta.get("compare_at_price", int(actual_price) * 2)),
        tags=tags,
        product_type=type_info["label"],
        vendor="AI Digital Store",
        content_text=content_text,
    )


def _build_content_prompt(theme: str, product_type: str) -> str:
    if product_type == "prompt_pack":
        return f"""「{theme}」に関するChatGPT/Claudeプロンプト集を作成してください。

要件:
- プロンプト20個以上
- 各プロンプトに「用途」「プロンプト本文」「使用例」を含める
- 初心者でもすぐ使えるレベル
- マークダウン形式で出力"""

    elif product_type == "template":
        return f"""「{theme}」に関するビジネステンプレート集を作成してください。

要件:
- テンプレート10種類以上
- 各テンプレートに「用途」「テンプレート本文（穴埋め形式）」「記入例」を含める
- そのままコピペで使えるレベル
- マークダウン形式で出力"""

    else:  # guide
        return f"""「{theme}」の実践ガイドを作成してください。

要件:
- ステップバイステップで解説（10ステップ以上）
- 各ステップに具体的なアクション・ツール・注意点を含める
- 初心者が0から実践できるレベル
- マークダウン形式で出力"""


def _build_shopify_payload(product: GeneratedProduct) -> dict:
    # デジタル商品：在庫管理なし・追跡なし
    variant = {
        "price": product.price,
        "compare_at_price": product.compare_at_price,
        "inventory_management": None,  # デジタル商品は在庫管理不要
        "requires_shipping": False,
        "taxable": True,
    }
    return {
        "title": product.title,
        "body_html": product.body_html,
        "vendor": product.vendor,
        "product_type": product.product_type,
        "tags": product.tags,
        "status": "active",
        "published": True,
        "variants": [variant],
    }
