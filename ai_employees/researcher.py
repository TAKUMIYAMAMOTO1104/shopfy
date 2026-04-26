"""リサーチ部長 ── 健康・美容ガジェットのトレンド商品候補を発掘する。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_employees.base import AIEmployee, EmployeeResult


class Researcher(AIEmployee):
    JOB_TITLE = "リサーチ部長"

    SYSTEM_PROMPT = """あなたは年商50億円のグローバルEC企業「BeautyTech Lab」のリサーチ部長です。
CEOはジョブズ氏。あなたの直属の上司です。

【あなたの責務】
健康・美容ガジェット領域における「次に売れる」商品候補を発掘し、構造化データとしてCEOに提出することです。
売れる根拠・想定原価・想定販売価格・参入難易度を冷静に判定する。妄想は禁止。

【取り扱いカテゴリ】
- スキンケアデバイス (LED美顔器、超音波クレンザー、EMSリフター 等)
- ヘアケアガジェット (頭皮マッサージャー、イオンドライヤー周辺 等)
- ボディケア (筋膜リリースガン、温冷ローラー 等)
- 口腔ケア (電動歯ブラシ、口臭ケアデバイス 等)
- 睡眠/ウェルネス (アイマスク型デバイス、姿勢矯正ガジェット 等)

【判定軸 (各5点満点)】
1. trend_score: トレンド勢い (TikTok/Instagram/Amazon等の話題性)
2. margin_score: 利益率 (中国仕入想定、想定原価対小売価格)
3. competition_score: 参入容易性 (競合少ないほど高い)
4. shipping_score: 物流容易性 (小型軽量・電池規制クリアほど高い)
5. brand_fit_score: ミニマル・プレミアムなブランド像との相性

【絶対ルール】
- 月予算10万円(うち仕入れ3万円)で回せるスケールを意識する
- 日本市場・英語圏(US/UK/AU)両方で売れる商品を優先する
- 法規制リスクのあるもの(医療機器扱い等)は除外
- 同じカテゴリばかりに偏らない (5商品なら最低3カテゴリに分散)
- 出力はJSONオブジェクトのみ。schemaは下記:

{
  "research_date": "YYYY-MM-DD",
  "candidates": [
    {
      "internal_code": "BTL-XXX",                 // 社内管理コード (BTL-001から連番)
      "category": "skincare|haircare|bodycare|oralcare|wellness",
      "title_jp": "日本語商品名 (40字以内)",
      "title_en": "English product name (60 chars max)",
      "core_concept": "1文で言える商品コンセプト (日本語)",
      "estimated_cost_jpy": 整数,                 // 1個あたり想定仕入原価
      "suggested_price_jpy": 整数,                // 日本市場想定小売価格
      "suggested_price_usd": 数値,                // 英語圏小売 (USD)
      "scores": {
        "trend": 1-5,
        "margin": 1-5,
        "competition": 1-5,
        "shipping": 1-5,
        "brand_fit": 1-5
      },
      "total_score": 5-25,                        // scoresの合計
      "rationale": "なぜ売れるか、3〜5文の根拠",
      "target_persona": "想定顧客像を1文で",
      "key_features": ["訴求ポイント1", "訴求ポイント2", "訴求ポイント3"],
      "risks": ["想定リスク1", "想定リスク2"]
    }
  ],
  "top_pick_code": "最も推奨する商品のinternal_code",
  "ceo_brief": "CEO向け200字以内のサマリー (日本語)"
}

数値は必ず数値型で出力すること(文字列禁止)。"""

    def run(
        self,
        n_products: int = 5,
        avoid_codes: list[str] | None = None,
        out_dir: str = "data/candidates",
    ) -> EmployeeResult:
        avoid_codes = avoid_codes or []
        avoid_text = (
            f"\n既出のため除外する社内コード: {', '.join(avoid_codes)}"
            if avoid_codes else ""
        )
        prompt = (
            f"本日({datetime.now():%Y-%m-%d})時点での商品候補を{n_products}件、"
            f"上記スキーマに従って提出してください。"
            f"{avoid_text}"
        )
        result = self._ask(prompt, max_tokens=6000)

        # 永続化: data/candidates/YYYY-MM-DD.json
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        out_path = Path(out_dir) / f"{datetime.now():%Y-%m-%d}.json"
        out_path.write_text(
            json.dumps(result.output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result.notes.append(f"候補リストを保存: {out_path}")
        return result

    # シミュレーション応答 (Claude APIなしで動作確認するため)
    def _simulated_response(self, user_prompt: str) -> EmployeeResult:
        sim = {
            "research_date": datetime.now().strftime("%Y-%m-%d"),
            "candidates": [
                {
                    "internal_code": "BTL-001",
                    "category": "skincare",
                    "title_jp": "ミニマルLED美顔マスク Aura One",
                    "title_en": "Aura One Minimal LED Beauty Mask",
                    "core_concept": "在宅5分で集中ケアができる軽量LEDマスク",
                    "estimated_cost_jpy": 2800,
                    "suggested_price_jpy": 12800,
                    "suggested_price_usd": 89.0,
                    "scores": {"trend": 5, "margin": 4, "competition": 3, "shipping": 4, "brand_fit": 5},
                    "total_score": 21,
                    "rationale": "TikTokで'home facial'タグが急伸。粗利4.5倍を確保しつつ参入余地が残る。",
                    "target_persona": "20代後半〜30代前半・美容感度高めの女性",
                    "key_features": ["軽量160g", "USB-C充電", "3波長LED"],
                    "risks": ["医療機器表現NG", "電池航空輸送"]
                },
                {
                    "internal_code": "BTL-002",
                    "category": "bodycare",
                    "title_jp": "ポケット筋膜ローラー Knead Mini",
                    "title_en": "Knead Mini Pocket Fascia Roller",
                    "core_concept": "デスクワーカー向けの手のひらサイズ筋膜リリース",
                    "estimated_cost_jpy": 1100,
                    "suggested_price_jpy": 4980,
                    "suggested_price_usd": 34.0,
                    "scores": {"trend": 4, "margin": 5, "competition": 4, "shipping": 5, "brand_fit": 4},
                    "total_score": 22,
                    "rationale": "電池不要で物流リスクゼロ。粗利率高く、リモートワーク需要に乗れる。",
                    "target_persona": "30代会社員・腰肩こりに悩む層",
                    "key_features": ["100g以下", "電池不要", "シリコン素材"],
                    "risks": ["差別化が外観頼み"]
                },
                {
                    "internal_code": "BTL-003",
                    "category": "wellness",
                    "title_jp": "重力アイマスク Sleep Cloud",
                    "title_en": "Sleep Cloud Weighted Eye Mask",
                    "core_concept": "重さで眼精疲労を緩和する睡眠特化アイマスク",
                    "estimated_cost_jpy": 600,
                    "suggested_price_jpy": 3480,
                    "suggested_price_usd": 24.0,
                    "scores": {"trend": 4, "margin": 5, "competition": 3, "shipping": 5, "brand_fit": 4},
                    "total_score": 21,
                    "rationale": "電子部品なしで返品率低い。睡眠系はAmazonで安定需要。",
                    "target_persona": "在宅勤務の30〜40代男女",
                    "key_features": ["260g重量設計", "コットン100%", "洗濯可"],
                    "risks": ["類似品多数"]
                },
                {
                    "internal_code": "BTL-004",
                    "category": "oralcare",
                    "title_jp": "携帯マウスウォッシュ Mist Pen",
                    "title_en": "Mist Pen Portable Mouthwash",
                    "core_concept": "ペン型のスプレー式マウスウォッシュデバイス",
                    "estimated_cost_jpy": 900,
                    "suggested_price_jpy": 3980,
                    "suggested_price_usd": 28.0,
                    "scores": {"trend": 3, "margin": 4, "competition": 4, "shipping": 4, "brand_fit": 4},
                    "total_score": 19,
                    "rationale": "口臭ケア市場は安定。客単価UPの定期消耗液で粗利を積める。",
                    "target_persona": "営業職・出張族",
                    "key_features": ["ペン型携帯", "USB-C充電", "詰替リフィル"],
                    "risks": ["薬機法表現要注意"]
                },
                {
                    "internal_code": "BTL-005",
                    "category": "haircare",
                    "title_jp": "頭皮ブラシ Scalp Halo",
                    "title_en": "Scalp Halo Sonic Head Brush",
                    "core_concept": "音波振動で頭皮をケアするシャンプー併用ブラシ",
                    "estimated_cost_jpy": 1400,
                    "suggested_price_jpy": 5980,
                    "suggested_price_usd": 42.0,
                    "scores": {"trend": 4, "margin": 4, "competition": 3, "shipping": 4, "brand_fit": 4},
                    "total_score": 19,
                    "rationale": "シャンプー時間に組み込めるためリピート訴求しやすい。",
                    "target_persona": "薄毛予兆を意識する30〜50代男性",
                    "key_features": ["IPX7防水", "サブスク化可", "180g"],
                    "risks": ["医療効果訴求NG"]
                }
            ],
            "top_pick_code": "BTL-002",
            "ceo_brief": "(SIMULATION) 利益率と物流容易性に優れるBTL-002を主軸に、トレンド性のあるBTL-001を集客導線として展開推奨。"
        }
        return EmployeeResult(
            employee=self.JOB_TITLE,
            output=sim,
            model=f"{self.model} [SIM]",
            notes=["シミュレーションモード: APIコール無し"],
        )
