#!/usr/bin/env python3
"""
Shopifyアクセストークン取得（ブラウザ手動認証方式）

使い方:
  python get_token.py --shop YOUR_SHOP.myshopify.com --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET

1. 表示されたURLをブラウザで開く
2. Shopifyでインストールを承認
3. リダイレクト後のURLをコピーして貼り付ける
"""

import argparse
import os
import secrets
import sys
import urllib.parse

import requests
from dotenv import load_dotenv, set_key

load_dotenv()

SCOPES       = "write_products,read_products,write_inventory,read_inventory,read_orders"
REDIRECT_URI = "https://example.com/callback"


def main():
    parser = argparse.ArgumentParser(description="Shopify OAuthトークン取得")
    parser.add_argument("--shop",          default=os.getenv("SHOPIFY_STORE", ""),         help="ストアドメイン")
    parser.add_argument("--client-id",     default=os.getenv("SHOPIFY_CLIENT_ID", ""),     help="アプリのClient ID")
    parser.add_argument("--client-secret", default=os.getenv("SHOPIFY_CLIENT_SECRET", ""), help="アプリのClient Secret")
    args = parser.parse_args()

    shop          = args.shop.strip().replace("https://", "").rstrip("/")
    client_id     = args.client_id.strip()
    client_secret = args.client_secret.strip()

    if not shop or not client_id or not client_secret:
        print("エラー: --shop, --client-id, --client-secret を指定してください")
        print("\n使い方:")
        print("  python get_token.py --shop YOUR_SHOP.myshopify.com --client-id CLIENT_ID --client-secret CLIENT_SECRET")
        sys.exit(1)

    state = secrets.token_hex(16)

    auth_url = (
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={client_id}"
        f"&scope={urllib.parse.quote(SCOPES)}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&state={state}"
        f"&grant_options[]=offline"
    )

    print("\n" + "=" * 60)
    print("Shopify 認証URL")
    print("=" * 60)
    print("\n以下のURLをブラウザで開いてください:\n")
    print(f"  {auth_url}")
    print("\n承認後、リダイレクトされたURL全体をアドレスバーからコピーして")
    print("以下に貼り付けてください（エラーページでも構いません）:")
    print("=" * 60 + "\n")

    callback_url = input("リダイレクトURL: ").strip()

    parsed    = urllib.parse.urlparse(callback_url)
    params    = urllib.parse.parse_qs(parsed.query)
    code      = params.get("code",  [""])[0]
    got_state = params.get("state", [""])[0]

    if not code:
        print("\nエラー: URLにcodeパラメータが見つかりません。")
        sys.exit(1)

    if got_state != state:
        print("\nエラー: stateが一致しません。URLが改ざんされている可能性があります。")
        sys.exit(1)

    print("\nアクセストークンを取得中...")
    resp = requests.post(
        f"https://{shop}/admin/oauth/access_token",
        json={"client_id": client_id, "client_secret": client_secret, "code": code},
        timeout=15,
    )

    if resp.status_code != 200:
        print(f"\nエラー: トークン取得失敗 ({resp.status_code}): {resp.text}")
        sys.exit(1)

    token = resp.json().get("access_token", "")
    if not token:
        print("\nエラー: レスポンスにaccess_tokenが含まれていません")
        sys.exit(1)

    env_path = ".env"
    if not os.path.exists(env_path):
        open(env_path, "w").close()
    set_key(env_path, "SHOPIFY_STORE", shop)
    set_key(env_path, "SHOPIFY_TOKEN", token)

    print(f"\n✅ 認証成功！")
    print(f"   ストア : {shop}")
    print(f"   トークン: {token[:12]}...  (.envに保存済み)")
    print(f"\n接続テスト:")
    print(f"  python shopify_manager.py export --output test.csv --limit 5")


if __name__ == "__main__":
    main()
