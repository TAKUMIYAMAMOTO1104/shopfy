#!/usr/bin/env python3
"""
Shopify OAuth認証トークン自動取得スクリプト

使い方:
  python setup_auth.py --shop xm-2031.myshopify.com --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET

実行後にブラウザでURLを開くとトークンが自動取得され .env に保存されます。
"""

import argparse
import hashlib
import hmac
import http.server
import json
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv, set_key

SCOPES = "write_products,read_products,write_inventory,read_inventory,read_orders"
REDIRECT_PORT = 3000
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"

_state = secrets.token_hex(16)
_received_token: dict = {}
_server_done = threading.Event()


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # ログ抑制

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith("/callback"):
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)

        # stateの検証
        received_state = params.get("state", [""])[0]
        if received_state != _state:
            self._respond(400, "<h1>状態パラメータが無効です。やり直してください。</h1>")
            return

        code = params.get("code", [""])[0]
        shop = params.get("shop", [""])[0]

        if not code:
            self._respond(400, "<h1>認証コードが取得できませんでした。</h1>")
            return

        # アクセストークン取得
        token_url = f"https://{shop}/admin/oauth/access_token"
        resp = requests.post(token_url, json={
            "client_id": self.server.client_id,
            "client_secret": self.server.client_secret,
            "code": code,
        }, timeout=15)

        if resp.status_code != 200:
            self._respond(500, f"<h1>トークン取得失敗: {resp.text}</h1>")
            return

        data = resp.json()
        _received_token["access_token"] = data.get("access_token", "")
        _received_token["shop"] = shop

        self._respond(200, """
        <html><head><meta charset="utf-8"></head><body>
        <h1>✅ 認証成功！</h1>
        <p>トークンを .env ファイルに保存しました。このウィンドウを閉じてください。</p>
        </body></html>
        """)
        _server_done.set()

    def _respond(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


def run_server(client_id: str, client_secret: str):
    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), CallbackHandler)
    server.client_id = client_id
    server.client_secret = client_secret
    server.timeout = 300  # 5分タイムアウト
    while not _server_done.is_set():
        server.handle_request()


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Shopify OAuth認証トークン自動取得")
    parser.add_argument("--shop", default=os.getenv("SHOPIFY_STORE", ""), help="ストアのドメイン (例: mystore.myshopify.com)")
    parser.add_argument("--client-id", default=os.getenv("SHOPIFY_CLIENT_ID", ""), help="アプリのClient ID")
    parser.add_argument("--client-secret", default=os.getenv("SHOPIFY_CLIENT_SECRET", ""), help="アプリのClient Secret")
    args = parser.parse_args()

    shop = args.shop.strip().replace("https://", "").rstrip("/")
    client_id = args.client_id.strip()
    client_secret = args.client_secret.strip()

    if not shop or not client_id or not client_secret:
        print("エラー: --shop, --client-id, --client-secret を指定してください")
        print("\n使い方:")
        print("  python setup_auth.py --shop xm-2031.myshopify.com --client-id CLIENT_ID --client-secret CLIENT_SECRET")
        sys.exit(1)

    # ローカルサーバーをバックグラウンドで起動
    thread = threading.Thread(target=run_server, args=(client_id, client_secret), daemon=True)
    thread.start()

    # OAuth URL生成
    auth_url = (
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={client_id}"
        f"&scope={urllib.parse.quote(SCOPES)}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&state={_state}"
        f"&grant_options[]=offline"
    )

    print("\n" + "="*60)
    print("Shopify OAuth認証")
    print("="*60)
    print("\n以下のURLをブラウザで開いてShopifyにログインしてください:\n")
    print(f"  {auth_url}\n")

    # ブラウザを自動で開く（環境によっては動かない場合あり）
    try:
        webbrowser.open(auth_url)
        print("ブラウザを自動で開きました。")
    except Exception:
        print("ブラウザの自動起動に失敗しました。上記URLを手動で開いてください。")

    print("\n認証完了を待っています... (5分でタイムアウト)")
    print("="*60)

    _server_done.wait(timeout=300)

    if not _received_token.get("access_token"):
        print("\nタイムアウトまたは認証失敗。やり直してください。")
        sys.exit(1)

    token = _received_token["access_token"]
    shop_domain = _received_token["shop"]

    # .env に保存
    env_path = ".env"
    if not os.path.exists(env_path):
        open(env_path, "w").close()

    set_key(env_path, "SHOPIFY_STORE", shop_domain)
    set_key(env_path, "SHOPIFY_TOKEN", token)

    print(f"\n✅ 認証成功！")
    print(f"   ストア: {shop_domain}")
    print(f"   トークン: {token[:12]}... (.envに保存済み)")
    print(f"\n次のコマンドで接続テストできます:")
    print(f"  python shopify_manager.py export --output test.csv --limit 5")


if __name__ == "__main__":
    main()
