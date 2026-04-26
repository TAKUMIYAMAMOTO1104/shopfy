"""トレンドリサーチ部長 ── ビジネス・自己啓発領域のバズり候補を発掘する。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_employees.base import AIEmployee, EmployeeResult


class TrendResearcher(AIEmployee):
    JOB_TITLE = "トレンドリサーチ部長"
    HANDLE = "@researcher"

    SYSTEM_PROMPT = """あなたは「ContentLab Tokyo」のトレンドリサーチ部長です。
CEOはジョブズ氏。あなたの直属の上司です。

【会社の事業】
顔出しなしのYouTube長尺(8〜12分)とShorts/TikTok/Reels(60秒)を
**ビジネス・自己啓発・キャリア・副業** ジャンルで日英両市場に展開する
コンテンツ工場「ContentLab Tokyo」を運営しています。

【あなたの責務】
本日「動画化したら確実に伸びる」トピック候補を発掘し、構造化データで脚本家に渡す。
「再生数が伸びる」だけでなく「広告フレンドリー」「ストック性(ロングテール)」も
バランスする。妄想は禁止。各スコアの根拠を持つ。

【取り扱う主要テーマ群】
- 副業・サイドハッスル (新興職種・収益モデル・税務)
- 生産性 / タイムマネジメント / 集中力 / 朝活
- リーダーシップ / マネジメント / 人間関係
- メンタルモデル / 思考法 / 意思決定
- お金・投資・キャリア戦略
- 学び方 / 読書 / 習慣化

【判定軸 (各5点満点)】
1. viral_score: 拡散ポテンシャル (フック強度・トレンド)
2. evergreen_score: ストック性 (1年後も再生され続けるか)
3. monetization_score: 高単価アフィリ・スポンサー親和性
4. ad_friendliness: YouTube広告ガイドライン適合 (デリケート話題は減点)
5. brand_fit_score: 「落ち着いた権威性」というブランド像との相性

【絶対ルール】
- 政治的に二極化する話題は除外 (ad_friendlinessが下がる)
- 医療効果・投資断定など法規制リスクのある主張は除外
- 同じテーマ群に偏らない (3トピックなら最低2テーマ群に分散)
- 出力はJSONのみ。schemaは下記。

{
  "research_date": "YYYY-MM-DD",
  "topics": [
    {
      "internal_code": "CTL-XXX",                  // 社内管理コード (CTL-001から連番)
      "theme_group": "side_hustle|productivity|leadership|mental_model|money|learning",
      "title_jp": "日本語仮タイトル (40字以内・クリックされる)",
      "title_en": "English working title (60 chars max)",
      "core_thesis": "1文で言える主張・気づき (日本語)",
      "viral_hook": "最初の5秒で視聴者を掴むフック (日本語・1文)",
      "audience_persona": "想定視聴者像 (1文)",
      "scores": {
        "viral": 1-5,
        "evergreen": 1-5,
        "monetization": 1-5,
        "ad_friendliness": 1-5,
        "brand_fit": 1-5
      },
      "total_score": 5-25,
      "supporting_points": ["主張を支える論点1", "論点2", "論点3"],
      "rationale": "なぜ今この話題が伸びるか・3〜5文の根拠",
      "risks": ["想定リスク1", "想定リスク2"]
    }
  ],
  "top_pick_code": "本日着手すべきトピックのinternal_code (1つ)",
  "ceo_brief": "CEO向け200字以内のサマリー (日本語)",
  "chat_post": {
    "text": "@scriptwriter 向けハンドオフ込みの150字以内発言",
    "mentions": ["@scriptwriter"],
    "kind": "handoff"
  }
}

数値は数値型で出力すること(文字列禁止)。"""

    def run(
        self,
        n_topics: int = 3,
        avoid_codes: list[str] | None = None,
        out_dir: str = "data/content/trends",
        workspace=None,
    ) -> EmployeeResult:
        avoid_codes = avoid_codes or []
        avoid_text = (
            f"\n既出のため除外する社内コード: {', '.join(avoid_codes)}"
            if avoid_codes else ""
        )
        ctx = workspace.context_for(self.HANDLE) if workspace else ""
        prompt = (
            f"本日({datetime.now():%Y-%m-%d})時点で動画化価値のある"
            f"ビジネス・自己啓発トピック候補を{n_topics}件、上記スキーマで提出してください。"
            f"{avoid_text}\n\n"
            f"【ワークスペース・コンテキスト】\n{ctx}"
        )
        result = self._ask(prompt, max_tokens=4000)

        Path(out_dir).mkdir(parents=True, exist_ok=True)
        out_path = Path(out_dir) / f"{datetime.now():%Y-%m-%d}.json"
        out_path.write_text(
            json.dumps(result.output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result.notes.append(f"トレンド候補を保存: {out_path}")
        if workspace is not None:
            self._post_chat_from_output(workspace, result.output)
        return result

    def _simulated_response(self, user_prompt: str) -> EmployeeResult:
        sim = {
            "research_date": datetime.now().strftime("%Y-%m-%d"),
            "topics": [
                {
                    "internal_code": "CTL-001",
                    "theme_group": "productivity",
                    "title_jp": "「やる気」に頼るのをやめた瞬間、すべてが回り始めた",
                    "title_en": "The Day I Stopped Relying on Motivation",
                    "core_thesis": "意志力ではなく環境設計が行動を生む",
                    "viral_hook": "やる気が出ないのはあなたのせいじゃない。仕組みのせいだ。",
                    "audience_persona": "30代会社員・自己改善願望が強いが続かない層",
                    "scores": {"viral": 5, "evergreen": 5, "monetization": 4, "ad_friendliness": 5, "brand_fit": 5},
                    "total_score": 24,
                    "supporting_points": ["意志力は有限資源", "環境を変えれば習慣が変わる", "If-Thenプランニングの威力"],
                    "rationale": "BJ Fogg・James Clearの研究を背景にできる安定テーマ。検索ボリューム高くロングテール期待。",
                    "risks": ["既出感あるので切り口で勝負"]
                },
                {
                    "internal_code": "CTL-002",
                    "theme_group": "side_hustle",
                    "title_jp": "AI時代に「個人が稼ぐ」3つの新しい型",
                    "title_en": "3 New Income Models for the AI Era",
                    "core_thesis": "労働時間ではなく仕組みを売る時代",
                    "viral_hook": "副業=時間切売り、はもう古い。AIで個人がレバレッジを持てる時代だ。",
                    "audience_persona": "30〜40代・副業を真剣に検討する会社員",
                    "scores": {"viral": 5, "evergreen": 4, "monetization": 5, "ad_friendliness": 5, "brand_fit": 5},
                    "total_score": 24,
                    "supporting_points": ["デジタル製品", "オーディエンス資産", "AIエージェント運用"],
                    "rationale": "AI×副業は検索急増、高単価アフィリ(Notion/各種ツール)親和性◎",
                    "risks": ["稼げる断定を避ける必要"]
                },
                {
                    "internal_code": "CTL-003",
                    "theme_group": "mental_model",
                    "title_jp": "優秀な人が必ず知っている「逆算思考」の落とし穴",
                    "title_en": "The Hidden Trap of 'Backwards Planning' Top Performers Know",
                    "core_thesis": "ゴール起点思考は強力だが、創発を殺すリスクがある",
                    "viral_hook": "逆算思考で目標達成したのに、虚しい。それは設計ミスかもしれない。",
                    "audience_persona": "目標管理に疑問を感じる中堅ビジネスパーソン",
                    "scores": {"viral": 4, "evergreen": 5, "monetization": 3, "ad_friendliness": 5, "brand_fit": 5},
                    "total_score": 22,
                    "supporting_points": ["逆算の盲点", "創発思考との両立", "OKR的運用"],
                    "rationale": "上位5%層に深く刺さる。中級者向けで競合も少ない。",
                    "risks": ["万人受けはしない・再生伸び鈍い可能性"]
                }
            ],
            "top_pick_code": "CTL-001",
            "ceo_brief": "(SIMULATION) 本日の最有力はCTL-001(意志力 vs 環境設計)。再生・ストック・広告適合すべて満点。CTL-002は高単価アフィリ導線として並走推奨。",
            "chat_post": {
                "text": "@scriptwriter 本日のtop_pickはCTL-001「やる気に頼るのをやめた瞬間〜」。viral 5/5・evergreen 5/5。長尺マスターから3 Shorts派生で頼む。",
                "mentions": ["@scriptwriter"],
                "kind": "handoff",
            }
        }
        return EmployeeResult(
            employee=self.JOB_TITLE,
            output=sim,
            model=f"{self.model} [SIM]",
            notes=["シミュレーションモード: APIコール無し"],
        )
