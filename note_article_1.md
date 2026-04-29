# Shopify商品管理を全自動化！Pythonで作った社内ツール「shopfy」を公開します

こんにちは。

Shopifyでストアを運営していると、こんな悩みありませんか？

- 商品が増えてきて、管理画面からの登録がツラい
- 仕入れ価格が変動するたびに、何百件もの商品を手作業で更新している
- 在庫数の同期が追いつかず、欠品やオーバーセルが発生する
- CSVインポート機能では細かい制御ができない

私もまったく同じ悩みを抱えていたので、**ShopifyのAdmin APIをラップしたPython製の管理ツール**を自作しました。今回はそれを `shopfy` という名前で公開したので、ご紹介します。

---

## 何ができるのか

CSV1枚あれば、Shopifyに対して以下の操作を一括で実行できます。

| サブコマンド | できること |
| --- | --- |
| `create` | CSVから商品を一括**登録** (バリアント対応) |
| `update` | 既存商品の**更新** (価格だけ・在庫だけといった部分更新もOK) |
| `delete` | 商品の**アーカイブ／削除** |
| `sync-inventory` | 在庫数の**一括同期** |
| `export` | 既存商品をCSVに**エクスポート** |

たとえば商品登録なら、こんな感じで叩くだけです。

```bash
python shopify_manager.py create products.csv --variants
```

「いきなり本番に流すのは怖い」という方のために、すべてのコマンドに `--dry-run` を用意しました。APIを叩かずに、CSVのパース結果と送信予定のペイロードだけを確認できます。

```bash
python shopify_manager.py create products.csv --dry-run
```

---

## こだわりポイント

### 1. レート制限をきっちり守る

ShopifyのREST Admin APIは「2リクエスト/秒」というレート制限があります。これを超えると `429 Too Many Requests` で叩き返されるので、ツール側でトークンバケット方式のレートリミッターを実装しています。

```python
class RateLimiter:
    """トークンバケット方式レート制限: 2 req/秒"""

    def __init__(self, calls_per_second: float = 2.0):
        self._min_interval = 1.0 / calls_per_second
        self._last_called = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_called
            remaining = self._min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
            self._last_called = time.monotonic()
```

シンプルですが、これだけで「動いているうちに止まった」が激減しました。

### 2. 失敗してもリトライ

ネットワーク瞬断や `5xx` エラーで処理が止まると、数千件の登録の途中で失敗していたときに泣くことになります。`tenacity` で**指数バックオフ付きの自動リトライ**を組み込み、`429 / 500 / 502 / 503 / 504` は最大5回まで自動で再試行します。

### 3. ページネーションを意識しないで使える

商品が250件を超えると、Shopify APIは `Link` ヘッダーの `page_info` を辿る必要があります。これを毎回手書きするのは面倒なので、内部で吸収しました。利用側は `client.get_all_products()` を呼ぶだけで、何千件あっても全件取れます。

### 4. 失敗行だけCSVに吐き出せる

5000件の登録で3件だけ失敗した、というときに「どれが失敗したのか分からない」と詰みます。`--output-errors errors.csv` を付けると、失敗した行だけが原因コメント付きで別CSVに出力されるので、修正してそのまま再投入できます。

```bash
python shopify_manager.py create products.csv --output-errors errors.csv
# → 失敗だけ修正して
python shopify_manager.py create errors.csv
```

### 5. SKUからのルックアップをキャッシュ

`update` や `sync-inventory` は「SKUから商品/バリアントを引く」処理が必須なんですが、これを毎回API叩いてたら遅くて使い物になりません。一度引いたSKUは内部キャッシュに保持して、2回目以降は1リクエストで済むようにしてあります。

---

## 認証まわりも自動化

「Admin APIのアクセストークンって、どうやって取るんだっけ？」という最初のハードルが地味に高いので、ここも2種類の取得スクリプトを用意しました。

- `setup_auth.py` … OAuthフローで自動取得 (パートナーアプリ向け)
- `get_token.py` … ブラウザで手動承認したコードを貼るだけの簡易版

`.env` に `SHOPIFY_SHOP_NAME` と `SHOPIFY_ACCESS_TOKEN` をセットすればすぐ動きます。

```env
SHOPIFY_SHOP_NAME=mystore
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxx
```

---

## 実際の使用感

社内のオペレーションでは、こんな流れに置き換わりました。

**Before (管理画面ポチポチ)**
- 新商品登録: 1件あたり3〜5分 × 100件 = 半日仕事
- 価格改定: Excelで作って管理画面に貼り付け、ミスったら巻き戻し不可

**After (shopfy)**
- 新商品登録: CSVを準備して `create` 一発、5分で完了
- 価格改定: `update --field price --dry-run` で確認 → 本実行
- 万一失敗しても `--output-errors` で差分だけ再投入

「夜のうちに流しておけば朝には終わってる」運用ができるようになり、商品担当者のメンタルが見違えるほど良くなりました (本人談)。

---

## こんな人におすすめ

- Shopify商品が**数百〜数万件**規模で、管理画面では限界を感じている
- 仕入れ・在庫・価格を**外部システム (基幹/ERP/スプレッドシート) と同期**したい
- ShopifyのCSVインポートでは**かゆいところに手が届かない**と感じている
- Pythonが書けて、自社運用で**カスタムロジックを足したい**

---

## おわりに

「ECの裏側って、こんなに泥臭いの？」と何度も思いながら作りましたが、自動化が回り始めると本当に楽になります。

商品データの整形ロジックや、独自のカテゴリ変換、ブランド別の処理分岐などは、それぞれのストアで違うはず。**`commands/` 配下のサブコマンドを書き換えれば、自社運用にフィットさせやすい構成**にしてあるので、ぜひフォークして使ってみてください。

質問・改善要望はコメント欄かGitHubのIssueでお待ちしています。

それでは、よいShopifyライフを！

---

*この記事で紹介したツールはMITライセンスで公開しています。本番投入の前には必ず `--dry-run` で動作確認してくださいね。*
