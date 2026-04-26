"""マーチャンダイザー ── 商品候補を売れるShopify商品ページに変換しCSV化する。"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_employees.base import AIEmployee, EmployeeResult


# shopify_managerのcreateコマンドが要求するCSV列順 (products_sample.csv準拠)
CSV_COLUMNS = [
    "title", "body_html", "vendor", "product_type", "tags", "status",
    "price", "compare_at_price", "sku", "barcode", "inventory_quantity",
    "inventory_policy", "weight", "weight_unit",
    "option1_name", "option1_value", "image_url", "image_alt_text",
]


class Merchandiser(AIEmployee):
    JOB_TITLE = "マーチャンダイザー"

    SYSTEM_PROMPT = """あなたは「BeautyTech Lab」のマーチャンダイザーです。
リサーチ部長から提出された商品候補を、Shopifyに即時投入できる「売れる商品ページ」に仕上げる責務を負います。

【あなたが守るべきルール】
1. ブランドトーンは「ミニマル・プレミアム」(Apple的な簡潔さ + 高級感)
2. 説明文(body_html)は<p>タグでマークアップした2〜3段落の日本語コピー
3. 英語圏向けには別途英語の説明文を作成し、商品タイトルも英語版を用意する
4. tagsはカンマ区切り、5〜8個。SEOと回遊を意識する
5. SKUはinternal_codeから派生 (例: BTL-001 → BTL-001-JP / BTL-001-EN)
6. 価格はリサーチ部長の提示値を基本尊重 (税込前提、日本円・USD両対応)
7. compare_at_price は price の1.3〜1.6倍 (アンカー価格として)
8. 在庫は初期20個固定 (smallロット仕入想定)
9. 重量はスキンケア300g, ボディケア200g, 口腔/ヘア250g, ウェルネス400g目安

【絶対禁止事項】
- 薬機法に触れる効果効能表現 (「治る」「効く」「改善する」等)
- 医療機器とみなされる表現
- 不確かな最上級表現 (「世界最強」「日本一」等のエビデンスなし表現)

【出力スキーマ (JSON)】
{
  "products": [
    {
      "internal_code": "BTL-001",
      "jp": {
        "title": "日本語商品名",
        "body_html": "<p>...</p><p>...</p>",
        "vendor": "BeautyTech Lab",
        "product_type": "スキンケアデバイス|ボディケア|...",
        "tags": "tag1,tag2,tag3",
        "status": "active",
        "price": 整数,
        "compare_at_price": 整数,
        "sku": "BTL-XXX-JP",
        "inventory_quantity": 20,
        "inventory_policy": "deny",
        "weight": 数値,
        "weight_unit": "g",
        "image_alt_text": "代替テキスト"
      },
      "en": {
        "title": "English Product Name",
        "body_html": "<p>...</p><p>...</p>",
        "vendor": "BeautyTech Lab",
        "product_type": "Skincare Device|Bodycare|...",
        "tags": "tag1,tag2,tag3",
        "status": "active",
        "price": 数値 (USD・小数1桁),
        "compare_at_price": 数値,
        "sku": "BTL-XXX-EN",
        "inventory_quantity": 20,
        "inventory_policy": "deny",
        "weight": 数値,
        "weight_unit": "g",
        "image_alt_text": "Alt text in English"
      }
    }
  ],
  "ceo_brief": "今回のラインナップの戦略的位置づけ (200字以内)"
}

数値型は必ず数値で、HTMLは正しくエスケープすること。"""

    def run(
        self,
        candidates: dict[str, Any],
        out_dir: str = "data/csv_out",
    ) -> EmployeeResult:
        # リサーチ部長の出力をそのまま渡す
        prompt = (
            "以下のリサーチ部長の提出資料を元に、各候補商品について"
            "日本語版・英語版の商品ページデータをスキーマに沿って生成してください。\n\n"
            f"```json\n{json.dumps(candidates, ensure_ascii=False)}\n```"
        )
        result = self._ask(prompt, max_tokens=8000)

        # CSV書き出し
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        date = datetime.now().strftime("%Y-%m-%d")
        jp_path = Path(out_dir) / f"{date}_jp.csv"
        en_path = Path(out_dir) / f"{date}_en.csv"
        self._write_csv(jp_path, result.output.get("products", []), market="jp")
        self._write_csv(en_path, result.output.get("products", []), market="en")
        result.notes.append(f"日本語CSV: {jp_path}")
        result.notes.append(f"英語CSV: {en_path}")
        return result

    @staticmethod
    def _write_csv(path: Path, products: list[dict], market: str) -> None:
        rows = []
        for p in products:
            data = p.get(market, {})
            row = {col: data.get(col, "") for col in CSV_COLUMNS}
            # option1系は単一バリアント想定で空欄
            row.setdefault("option1_name", "")
            row.setdefault("option1_value", "")
            row.setdefault("image_url", data.get("image_url", ""))
            row.setdefault("barcode", "")
            rows.append(row)

        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    # シミュレーション応答
    def _simulated_response(self, user_prompt: str) -> EmployeeResult:
        # user_promptに埋め込まれた候補JSONを抜き出す (前後にコードフェンスあり)
        import re
        m = re.search(r"```json\s*(\{.*?\})\s*```", user_prompt, re.DOTALL)
        candidates = json.loads(m.group(1)) if m else {"candidates": []}

        products_out = []
        for c in candidates.get("candidates", []):
            code = c.get("internal_code", "BTL-XXX")
            jp_title = c.get("title_jp", "")
            en_title = c.get("title_en", "")
            price_jpy = c.get("suggested_price_jpy", 0)
            price_usd = c.get("suggested_price_usd", 0.0)
            category = c.get("category", "skincare")
            weight_map = {
                "skincare": 300, "bodycare": 200, "haircare": 250,
                "oralcare": 250, "wellness": 400,
            }
            ptype_map_jp = {
                "skincare": "スキンケアデバイス",
                "bodycare": "ボディケア",
                "haircare": "ヘアケア",
                "oralcare": "オーラルケア",
                "wellness": "ウェルネス",
            }
            ptype_map_en = {
                "skincare": "Skincare Device",
                "bodycare": "Bodycare",
                "haircare": "Haircare",
                "oralcare": "Oral Care",
                "wellness": "Wellness",
            }
            features_jp = "・".join(c.get("key_features", []))
            persona = c.get("target_persona", "")
            concept = c.get("core_concept", "")

            products_out.append({
                "internal_code": code,
                "jp": {
                    "title": jp_title,
                    "body_html": f"<p>{concept}。</p><p>{persona}に向けて設計された一品。</p><p>特徴: {features_jp}</p>",
                    "vendor": "BeautyTech Lab",
                    "product_type": ptype_map_jp.get(category, "美容ガジェット"),
                    "tags": f"{category},新着,日本発送,bdtech,minimal",
                    "status": "active",
                    "price": price_jpy,
                    "compare_at_price": int(price_jpy * 1.4),
                    "sku": f"{code}-JP",
                    "inventory_quantity": 20,
                    "inventory_policy": "deny",
                    "weight": weight_map.get(category, 300),
                    "weight_unit": "g",
                    "image_alt_text": f"{jp_title} メイン画像",
                },
                "en": {
                    "title": en_title,
                    "body_html": f"<p>{en_title}: a minimal device designed for daily routines.</p><p>Built for everyday use, ships globally.</p>",
                    "vendor": "BeautyTech Lab",
                    "product_type": ptype_map_en.get(category, "Beauty Gadget"),
                    "tags": f"{category},new,global,bdtech,minimal",
                    "status": "active",
                    "price": price_usd,
                    "compare_at_price": round(price_usd * 1.4, 2),
                    "sku": f"{code}-EN",
                    "inventory_quantity": 20,
                    "inventory_policy": "deny",
                    "weight": weight_map.get(category, 300),
                    "weight_unit": "g",
                    "image_alt_text": f"{en_title} main image",
                },
            })

        sim = {
            "products": products_out,
            "ceo_brief": "(SIMULATION) 全候補について日英両市場向けのページデータを生成。即出品可能。",
        }
        return EmployeeResult(
            employee=self.JOB_TITLE,
            output=sim,
            model=f"{self.model} [SIM]",
            notes=["シミュレーションモード"],
        )
