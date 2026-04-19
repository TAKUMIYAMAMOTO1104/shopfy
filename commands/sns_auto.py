"""SNS自動投稿コマンド

Claudeが宣伝文を生成しX(Twitter)に自動投稿する。

使い方:
  python shopify_manager.py sns-post --product-id 12345
  python shopify_manager.py sns-post --theme "ChatGPT副業" --dry-run
  python shopify_manager.py sns-post --daily  # 売れ筋商品を自動選択して投稿

環境変数:
  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
  SHOPIFY_STORE_URL  (例: https://xm-2031.myshopify.com)
"""

import json
import os
import random
from datetime import datetime
from pathlib import Path

from utils.logger import setup_logger

logger = setup_logger(__name__)

POST_LOG_PATH = Path("logs/sns_posts.jsonl")

HASHTAG_POOLS = [
    "#ChatGPT", "#AI副業", "#副業", "#稼ぐ方法", "#在宅ワーク",
    "#AI活用", "#プロンプト", "#自動化", "#ビジネス", "#デジタル商品",
    "#副収入", "#個人事業主", "#フリーランス", "#マネタイズ",
]


def run_sns_post(
    product_id: int | None = None,
    theme: str | None = None,
    dry_run: bool = False,
    daily: bool = False,
    store_url: str | None = None,
    client=None,
) -> bool:
    store_url = store_url or os.getenv("SHOPIFY_STORE_URL", "").rstrip("/")

    if daily and client:
        return _post_daily_best(client, store_url, dry_run)

    if product_id and client:
        product = client.get_product_by_id(product_id)
        if not product:
            logger.error(f"商品ID {product_id} が見つかりません")
            return False
        return _post_product(product, store_url, dry_run)

    if theme:
        return _post_theme_content(theme, store_url, dry_run)

    logger.error("--product-id, --theme, --daily のいずれかを指定してください")
    return False


def _post_daily_best(client, store_url: str, dry_run: bool) -> bool:
    """アクティブ商品からランダムに1件選んで投稿"""
    products = client.get_all_products({"status": "active", "limit": 50})
    if not products:
        logger.warning("投稿対象の商品が見つかりません")
        return False

    product = random.choice(products)
    logger.info(f"投稿対象: {product.get('title')}")
    return _post_product(product, store_url, dry_run)


def _post_product(product: dict, store_url: str, dry_run: bool) -> bool:
    """商品情報からツイート文を生成して投稿"""
    title = product.get("title", "")
    price = product.get("variants", [{}])[0].get("price", "")
    product_id = product.get("id")
    url = f"{store_url}/products/{product.get('handle', '')}" if store_url else ""

    tweet = _generate_product_tweet(title, price, url)
    return _post_tweet(tweet, dry_run, metadata={"product_id": product_id, "title": title})


def _post_theme_content(theme: str, store_url: str, dry_run: bool) -> bool:
    """テーマから教育コンテンツ型ツイートを生成して投稿"""
    tweet = _generate_educational_tweet(theme, store_url)
    return _post_tweet(tweet, dry_run, metadata={"theme": theme})


def _generate_product_tweet(title: str, price: str, url: str) -> str:
    from utils.ai_client import _get_client

    hashtags = " ".join(random.sample(HASHTAG_POOLS, 5))
    prompt = f"""以下のShopifyデジタル商品を宣伝するX(Twitter)投稿文を生成してください。

商品名: {title}
価格: ¥{price}
URL: {url}

要件:
- 140文字以内（URLは含めない）
- 冒頭に絵文字を使う
- 「今だけ」「限定」などの希少性を演出
- 具体的なベネフィットを1〜2個
- 投稿文のみ出力（説明不要）"""

    resp = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    tweet_body = resp.content[0].text.strip()

    # URL + ハッシュタグを追記
    parts = [tweet_body]
    if url:
        parts.append(url)
    parts.append(hashtags)
    return "\n\n".join(parts)


def _generate_educational_tweet(theme: str, store_url: str) -> str:
    from utils.ai_client import _get_client

    hashtags = " ".join(random.sample(HASHTAG_POOLS, 4))
    prompt = f"""「{theme}」に関する有益なX(Twitter)投稿文（教育コンテンツ型）を生成してください。

要件:
- 240文字以内
- 「知らないと損」「○○するだけで」などの導入
- 具体的なtips/数字を含める
- 最後に「詳細はプロフのリンクから」などのCTA
- 冒頭に絵文字
- 投稿文のみ出力"""

    resp = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    tweet_body = resp.content[0].text.strip()
    return f"{tweet_body}\n\n{hashtags}"


def _post_tweet(tweet: str, dry_run: bool, metadata: dict | None = None) -> bool:
    logger.info(f"生成ツイート:\n{tweet}")
    logger.info(f"文字数: {len(tweet)}")

    if dry_run:
        logger.info("[DRY-RUN] 実際の投稿はスキップ")
        _save_log(tweet, "dry_run", metadata)
        return True

    # X API v2 で投稿
    try:
        import tweepy

        api_key = os.getenv("X_API_KEY", "")
        api_secret = os.getenv("X_API_SECRET", "")
        access_token = os.getenv("X_ACCESS_TOKEN", "")
        access_secret = os.getenv("X_ACCESS_TOKEN_SECRET", "")

        if not all([api_key, api_secret, access_token, access_secret]):
            logger.warning(
                "X API認証情報が未設定です。.envに X_API_KEY / X_API_SECRET / "
                "X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET を設定してください"
            )
            _save_log(tweet, "skipped_no_auth", metadata)
            return False

        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        resp = client.create_tweet(text=tweet)
        tweet_id = resp.data["id"]
        logger.info(f"投稿完了: tweet_id={tweet_id}")
        _save_log(tweet, "posted", metadata, tweet_id=tweet_id)
        return True

    except ImportError:
        logger.error("tweepyが必要です: pip install tweepy")
        return False
    except Exception as e:
        logger.error(f"投稿失敗: {e}")
        _save_log(tweet, f"error:{e}", metadata)
        return False


def _save_log(tweet: str, status: str, metadata: dict | None, tweet_id: str | None = None) -> None:
    POST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "tweet_id": tweet_id,
        "tweet": tweet,
        **(metadata or {}),
    }
    with open(POST_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
