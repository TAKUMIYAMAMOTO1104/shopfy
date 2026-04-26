"""演出ディレクター ── 脚本にタイトル・サムネ・説明文・タグを与え本番投下できる形にする。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_employees.base import AIEmployee, EmployeeResult


class Director(AIEmployee):
    JOB_TITLE = "演出ディレクター"
    HANDLE = "@director"

    SYSTEM_PROMPT = """あなたは「ContentLab Tokyo」の演出ディレクター(Director)です。
脚本家から渡された脚本を、YouTube/TikTokに投下できる完全な制作パッケージに仕上げます。
編集者やAI動画ツール(Runway/Pika/HeyGen等)が、あなたの成果物だけを見て動画を組めるレベルの粒度で書く責務を負います。

【ブランド像】
落ち着いた権威性。Apple基調講演 × TED的トーン。説教臭くない、しかし軽くもない。

【あなたが各動画について必ず生成するもの】
1. **タイトルA/B案 5つ** ── 異なるフック戦略 (好奇心/逆張り/数字/質問/権威)
2. **サムネイル案 3つ** ── 各案について
   - composition: 配置のテキスト記述
   - text_overlay: サムネ上に置く日本語/英語テキスト (5〜9文字推奨)
   - image_prompt: Midjourney/DALL-E向けの英語プロンプト
   - color_palette: ブランドに合う配色 (例: deep navy + warm gold)
3. **説明文(description)** ── 動画概要 + チャプタータイムスタンプ + 関連リンクプレースホルダ
4. **タグ・ハッシュタグ** ── YouTube用15個 + Shorts/TikTok用5個
5. **チャプター(timestamps)** ── 長尺のみ。3〜5箇所
6. **ピン留めコメント** ── 視聴者エンゲージを促す1〜2文

【規律】
- タイトルは40字以内 (日本語) / 60 chars (英語)
- 説明文の最初の160字でクリック後の継続視聴を引き出す
- ハッシュタグは過度に詰めない (検索ノイズになる)
- サムネテキストはタイトルと完全一致させない (二重情報を避ける)
- センセーショナル禁止 ("絶対" "100%" "必ず稼げる" 等)

【出力スキーマ】
{
  "internal_code": "CTL-XXX",
  "packages": [
    {
      "label": "long_jp" | "long_en" | "shorts_jp_1" | "shorts_en_1" | ...,
      "platform": "youtube_long" | "youtube_shorts" | "tiktok" | "reels",
      "language": "jp" | "en",
      "title_variants": ["案A","案B","案C","案D","案E"],
      "recommended_title_index": 0,
      "thumbnails": [
        {
          "label": "thumb_a",
          "composition": "...",
          "text_overlay": "...",
          "image_prompt": "...",
          "color_palette": "..."
        }
      ],
      "description": "...",
      "tags": ["tag1", ...],
      "hashtags": ["#tag1", ...],
      "chapters": [
        {"time": "00:00", "title": "Hook"},
        {"time": "00:35", "title": "..."}
      ],
      "pinned_comment": "..."
    }
  ],
  "summary": "本日のラインナップに対する演出方針 (3文以内)",
  "chat_post": {
    "text": "@cfo 向け制作パッケージ完了報告 (120字以内)",
    "mentions": ["@cfo"],
    "kind": "handoff"
  }
}"""

    def run(
        self,
        scripts: dict[str, Any],
        out_dir: str = "data/content/production",
        workspace=None,
    ) -> EmployeeResult:
        ctx = workspace.context_for(self.HANDLE) if workspace else ""
        prompt = (
            "以下は脚本家から渡された脚本JSONです。"
            "長尺JP/EN・Shorts JP/EN各本に対し、上記スキーマで完全な制作パッケージを作ってください。\n\n"
            f"```json\n{json.dumps(scripts, ensure_ascii=False)}\n```\n\n"
            f"【ワークスペース・コンテキスト】\n{ctx}"
        )
        result = self._ask(prompt, max_tokens=10000)

        out = result.output
        code = out.get("internal_code", "CTL-XXX")
        date = datetime.now().strftime("%Y-%m-%d")
        base = Path(out_dir) / date / code
        base.mkdir(parents=True, exist_ok=True)
        (base / "production.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # オーナーが目検しやすいMarkdown概要も生成
        (base / "production_summary.md").write_text(
            self._render_summary_md(out), encoding="utf-8"
        )

        result.notes.append(f"制作パッケージ保存先: {base}")
        if workspace is not None:
            self._post_chat_from_output(workspace, out)
        return result

    @staticmethod
    def _render_summary_md(out: dict) -> str:
        lines = [f"# 制作パッケージ — {out.get('internal_code', '')}", ""]
        for p in out.get("packages", []):
            lines += [
                f"## {p.get('label', '')} ({p.get('platform', '')} / {p.get('language', '')})",
                "",
                "### Title Variants",
            ]
            for i, t in enumerate(p.get("title_variants", [])):
                marker = "★ " if i == p.get("recommended_title_index", 0) else "  "
                lines.append(f"- {marker}{t}")
            lines += ["", "### Thumbnails"]
            for t in p.get("thumbnails", []):
                lines += [
                    f"- **{t.get('label', '')}**: `{t.get('text_overlay', '')}` "
                    f"({t.get('color_palette', '')})",
                    f"  - prompt: {t.get('image_prompt', '')}",
                ]
            lines += ["", "### Description (preview)", p.get("description", "")[:300] + "...", ""]
            lines += ["### Hashtags", " ".join(p.get("hashtags", [])), ""]
        return "\n".join(lines)

    def _simulated_response(self, user_prompt: str) -> EmployeeResult:
        import re
        m = re.search(r"```json\s*(\{.*?\})\s*```", user_prompt, re.DOTALL)
        scripts = json.loads(m.group(1)) if m else {}
        code = scripts.get("internal_code", "CTL-XXX")

        def long_pkg(lang: str) -> dict:
            is_jp = lang == "jp"
            return {
                "label": f"long_{lang}",
                "platform": "youtube_long",
                "language": lang,
                "title_variants": (
                    [
                        "「やる気」を捨てた瞬間に人生が回り始めた話",
                        "意志力に頼るのは設計ミスです (脳科学が示す本当の正解)",
                        "続かないのはあなたのせいじゃない、3つの仕組みが解決する",
                        "成功者が共通して捨てている1つの習慣",
                        "やる気ゼロでも前に進める、研究で証明された3つの設計",
                    ] if is_jp else [
                        "I Stopped Relying on Motivation. Here's What Happened.",
                        "Willpower Is a Design Flaw. Here's the Fix.",
                        "Why Consistent People Don't Use Discipline (Research Inside)",
                        "The 3 Habits Top Performers Quietly Removed",
                        "Stop Pushing. Design It. (How Habits Actually Stick)",
                    ]
                ),
                "recommended_title_index": 1,
                "thumbnails": [
                    {
                        "label": "thumb_a",
                        "composition": "left half: bold 3-line text; right half: minimal photo of a desk with phone in another room",
                        "text_overlay": "意志力は設計ミス" if is_jp else "Willpower = Design Flaw",
                        "image_prompt": "Cinematic, minimalist desk scene, soft window light, deep navy and warm gold palette, 16:9, no people, sharp focus, editorial style",
                        "color_palette": "deep navy + warm gold + cream",
                    },
                    {
                        "label": "thumb_b",
                        "composition": "single bold word on left, contrasting fading word right",
                        "text_overlay": "やめる→進む" if is_jp else "STOP → MOVE",
                        "image_prompt": "Minimalist split composition, navy left and cream right, gold accent line, editorial typography mockup",
                        "color_palette": "deep navy + cream + gold",
                    },
                    {
                        "label": "thumb_c",
                        "composition": "running tank illustration with leak",
                        "text_overlay": "燃料切れの脳" if is_jp else "Empty Tank Brain",
                        "image_prompt": "Subtle illustration of a fuel gauge near empty, soft watercolor, navy and gold, white background",
                        "color_palette": "deep navy + warm gold",
                    },
                ],
                "description": (
                    ("続けられない原因は意志力ではなく、環境設計にあります。"
                     "ロイ・バウマイスター、ピーター・ゴルヴィッツァー、BJ Foggの研究が示す3つの設計原則を解説します。\n\n"
                     "00:00 ホック\n00:30 意志力は有限資源\n03:10 If-Thenプランニング\n06:20 環境設計\n09:00 まとめとCTA\n\n"
                     "🔗 参考: 関連プレイリストは概要欄1番目のリンク。\n\n"
                     "🎙 ContentLab Tokyo: ビジネス・自己啓発のロングテール考察。")
                    if is_jp else
                    ("If discipline keeps failing you, it isn't your fault — it's a design flaw. "
                     "Roy Baumeister, Peter Gollwitzer, and BJ Fogg show why systems beat willpower.\n\n"
                     "00:00 Hook\n00:30 Willpower is finite\n03:10 If-Then planning\n06:20 Design beats discipline\n09:00 Wrap & CTA\n\n"
                     "🔗 Linked playlist in the description.\n\n"
                     "🎙 ContentLab Tokyo: long-form essays on business and self-development.")
                ),
                "tags": [
                    "habit", "productivity", "self_improvement", "behavioral_science",
                    "motivation", "discipline", "atomic_habits", "bj_fogg", "willpower",
                    "if_then", "environment_design", "morning_routine", "focus", "consistency",
                    "high_performance",
                ],
                "hashtags": ["#productivity", "#habits", "#focus", "#selfimprovement", "#mindset"],
                "chapters": [
                    {"time": "00:00", "title": "Hook"},
                    {"time": "00:30", "title": "意志力は有限" if is_jp else "Willpower is finite"},
                    {"time": "03:10", "title": "If-Thenの設計"},
                    {"time": "06:20", "title": "環境で勝つ" if is_jp else "Design beats discipline"},
                    {"time": "09:00", "title": "CTA"},
                ],
                "pinned_comment": (
                    "今日1つだけ、トリガーを書いてくれた人をピン留めで紹介します。"
                    if is_jp else
                    "Comment your one trigger for today. I'll pin the best ones."
                ),
            }

        def shorts_pkg(lang: str, idx: int) -> dict:
            is_jp = lang == "jp"
            base_title_jp = [
                "やる気が出ないのは設計ミス",
                "続く人は環境で勝負している",
                "頑張るのを今日でやめる",
            ]
            base_title_en = [
                "Motivation isn't the problem.",
                "Consistent people use design, not discipline.",
                "Stop pushing. Design it.",
            ]
            t = base_title_jp[idx] if is_jp else base_title_en[idx]
            return {
                "label": f"shorts_{lang}_{idx+1}",
                "platform": "youtube_shorts" if is_jp else "youtube_shorts",
                "language": lang,
                "title_variants": [t, t + (" #shorts" if not is_jp else " #ショート"), t.replace("。", "?")],
                "recommended_title_index": 0,
                "thumbnails": [
                    {
                        "label": "thumb_main",
                        "composition": "center bold 1-line text on dark background",
                        "text_overlay": t[:9] + "…",
                        "image_prompt": "Vertical 9:16, navy background with bold gold text, no faces, editorial minimalism",
                        "color_palette": "deep navy + warm gold",
                    },
                ],
                "description": (
                    f"{t} 続きはチャンネルの長尺で。"
                    if is_jp else
                    f"{t} Full essay in the long-form on the channel."
                ),
                "tags": ["shorts", "productivity", "habit", "self_growth"],
                "hashtags": (
                    ["#shorts", "#習慣", "#自己改善", "#朝活", "#仕事術"]
                    if is_jp else
                    ["#shorts", "#habits", "#focus", "#productivity", "#selfimprovement"]
                ),
                "chapters": [],
                "pinned_comment": "コメントで一番続かなかった習慣を教えてください。"
                                 if is_jp else
                                 "Drop the habit you keep failing at in the comments.",
            }

        packages = [long_pkg("jp"), long_pkg("en")]
        for i in range(3):
            packages.append(shorts_pkg("jp", i))
            packages.append(shorts_pkg("en", i))

        sim = {
            "internal_code": code,
            "packages": packages,
            "summary": "(SIMULATION) 長尺は権威性タイトルB、サムネはthumb_b推奨。Shortsは縦型統一・色トーンを長尺と揃えてシリーズ感を演出。",
            "chat_post": {
                "text": f"@cfo 制作パッケージ完了。長尺JP/EN+Shorts6本=計8本ぶん。タイトルA/B、サムネ3案、説明文、タグまで揃えた。",
                "mentions": ["@cfo"],
                "kind": "handoff",
            },
        }
        return EmployeeResult(
            employee=self.JOB_TITLE,
            output=sim,
            model=f"{self.model} [SIM]",
            notes=["シミュレーションモード"],
        )
