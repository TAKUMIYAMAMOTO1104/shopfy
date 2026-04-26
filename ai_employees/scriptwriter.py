"""脚本家 ── 採択トピックを長尺マスター + 派生Shortsの脚本に仕上げる。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_employees.base import AIEmployee, EmployeeResult


class Scriptwriter(AIEmployee):
    JOB_TITLE = "脚本家"
    HANDLE = "@scriptwriter"

    SYSTEM_PROMPT = """あなたは「ContentLab Tokyo」の脚本家(Scriptwriter)です。
顔出しなしのナレーション主体動画の脚本を書き、長尺マスターから派生Shortsを切り出すことが責務です。

【会社の事業】
ビジネス・自己啓発・キャリア・副業ジャンルでYouTube長尺(8〜12分)とShorts(60秒)を
日本語マスター + 英語ローカライズ で量産するコンテンツ工場。

【書き方の規律】
- 冒頭5秒で必ず「フック」を打ち込む。視聴者の継続率はここで決まる。
- 1つの主張を、3〜5個のセクションに分けて深掘りする。
- セクション境界には「視聴維持の再フック」を入れる (例: でも、ここで多くの人が見落とすのが…)
- 専門語は避け、比喩・具体例を多用する。
- 動詞中心の文。情緒語より構造語。
- 最後はCTA(コメント欄での自己ワーク誘導)。
- 1本の長尺は日本語で約2,200〜2,800字、英語版は約350〜450 words(自然な尺感)。

【英語ローカライズ規律】
- 直訳禁止。論旨は同じだが、冒頭フックと事例は英語圏文化に合わせて差し替える。
- メートル法/通貨/年号など現地化する。

【Shorts派生規律】
- 長尺マスターから「最も鋭い3つのインサイト」を抜き出し、独立した60秒スクリプトとして成立させる。
- Shortsは1スクリプトあたり日本語約180字、英語約90 words。
- 各Shortsは「掴み(7秒) → 主張(35秒) → CTA/オチ(18秒)」の3部構成を守る。

【絶対禁止】
- 投資断定 (「絶対稼げる」等)
- 医療効果断定
- 他者人格攻撃
- 出典不明の数字を断定的に出すこと

【出力スキーマ (JSON)】
{
  "internal_code": "CTL-XXX",
  "long_form": {
    "jp": {
      "title": "日本語タイトル候補(暫定・最終はDirectorが決める)",
      "hook_5s": "冒頭5秒のセリフ",
      "intro": "イントロ段落 (200-300字)",
      "sections": [
        {"heading": "見出し1", "body": "本文 (400-600字)", "transition_hook": "次セクションへの再フック"},
        {"heading": "見出し2", "body": "...", "transition_hook": "..."},
        {"heading": "見出し3", "body": "...", "transition_hook": "..."}
      ],
      "outro": "アウトロ段落 (200-300字)",
      "cta": "コメント欄誘導CTA (1〜2文)",
      "approx_chars": 2500,
      "approx_runtime_seconds": 600
    },
    "en": {
      "title": "English title (working)",
      "hook_5s": "...",
      "intro": "...",
      "sections": [{"heading": "...", "body": "...", "transition_hook": "..."}],
      "outro": "...",
      "cta": "...",
      "approx_words": 400,
      "approx_runtime_seconds": 600
    }
  },
  "shorts_jp": [
    {"label": "shorts_jp_1", "hook_7s": "...", "main_35s": "...", "cta_18s": "...", "approx_chars": 180}
  ],
  "shorts_en": [
    {"label": "shorts_en_1", "hook_7s": "...", "main_35s": "...", "cta_18s": "...", "approx_words": 90}
  ],
  "ceo_brief": "なぜこの構成にしたかの戦略的意図 (200字以内)",
  "chat_post": {
    "text": "@director 向けの引き継ぎ発言 (150字以内)",
    "mentions": ["@director"],
    "kind": "handoff"
  }
}"""

    def run(
        self,
        topic: dict[str, Any],
        out_dir: str = "data/content/scripts",
        shorts_per_topic: int = 3,
        workspace=None,
    ) -> EmployeeResult:
        ctx = workspace.context_for(self.HANDLE) if workspace else ""
        prompt = (
            f"以下のトピックを長尺マスター(JP+EN) + 派生Shorts {shorts_per_topic}本(JP+EN)"
            f"の構成でスキーマに沿って書き上げてください。\n\n"
            f"```json\n{json.dumps(topic, ensure_ascii=False)}\n```\n\n"
            f"【ワークスペース・コンテキスト】\n{ctx}"
        )
        result = self._ask(prompt, max_tokens=12000)

        # 永続化: scripts/<date>/<code>/ 配下にMarkdownで保存
        out = result.output
        code = out.get("internal_code", "CTL-XXX")
        date = datetime.now().strftime("%Y-%m-%d")
        base = Path(out_dir) / date / code
        base.mkdir(parents=True, exist_ok=True)

        # JSON原本
        (base / "scripts.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 人間が読みやすいMarkdown
        for lang in ("jp", "en"):
            long = out.get("long_form", {}).get(lang, {})
            if long:
                (base / f"long_{lang}.md").write_text(
                    self._render_long_md(long, lang), encoding="utf-8"
                )
        for i, s in enumerate(out.get("shorts_jp", []), start=1):
            (base / f"shorts_jp_{i}.md").write_text(self._render_shorts_md(s, "jp"), encoding="utf-8")
        for i, s in enumerate(out.get("shorts_en", []), start=1):
            (base / f"shorts_en_{i}.md").write_text(self._render_shorts_md(s, "en"), encoding="utf-8")

        result.notes.append(f"脚本保存先: {base}")
        if workspace is not None:
            self._post_chat_from_output(workspace, out)
        return result

    @staticmethod
    def _render_long_md(long: dict, lang: str) -> str:
        lines = [
            f"# {long.get('title', '')}",
            "",
            f"_長尺・{lang.upper()}版・想定尺 {long.get('approx_runtime_seconds', '?')}s_",
            "",
            "## Hook (0-5s)",
            long.get("hook_5s", ""),
            "",
            "## Intro",
            long.get("intro", ""),
            "",
        ]
        for i, s in enumerate(long.get("sections", []), start=1):
            lines += [
                f"## Section {i}: {s.get('heading','')}",
                s.get("body", ""),
                "",
                f"_> 再フック: {s.get('transition_hook','')}_",
                "",
            ]
        lines += [
            "## Outro",
            long.get("outro", ""),
            "",
            "## CTA",
            long.get("cta", ""),
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _render_shorts_md(s: dict, lang: str) -> str:
        return "\n".join([
            f"# {s.get('label', '')} ({lang.upper()})",
            "",
            "## Hook (0-7s)",
            s.get("hook_7s", ""),
            "",
            "## Main (7-42s)",
            s.get("main_35s", ""),
            "",
            "## CTA / Punchline (42-60s)",
            s.get("cta_18s", ""),
            "",
        ])

    def _simulated_response(self, user_prompt: str) -> EmployeeResult:
        # トピックJSONを抽出
        import re
        m = re.search(r"```json\s*(\{.*?\})\s*```", user_prompt, re.DOTALL)
        topic = json.loads(m.group(1)) if m else {}
        code = topic.get("internal_code", "CTL-XXX")
        title_jp = topic.get("title_jp", "シミュレーション動画")
        title_en = topic.get("title_en", "Simulation Video")
        thesis = topic.get("core_thesis", "")
        hook = topic.get("viral_hook", "")

        sim = {
            "internal_code": code,
            "long_form": {
                "jp": {
                    "title": title_jp,
                    "hook_5s": hook or "やる気が出ないのは、あなたのせいじゃない。",
                    "intro": (
                        "「今日こそやる」と決めても、夕方には消えている。"
                        "そんな経験が積み重なると、自分はダメだと思ってしまう。"
                        "でも研究は逆を示している。問題はあなたではなく、環境設計の方にある。"
                    ),
                    "sections": [
                        {
                            "heading": "意志力は筋肉ではなく、有限の燃料だ",
                            "body": (
                                "ロイ・バウマイスターの研究が示したのは、人の意志力は1日のうちに枯渇するという事実だった。"
                                "朝、決断を重ねるほど夜の判断は鈍る。だから「夜に運動」「夜に勉強」は構造的に難しい。"
                                "対策はシンプルだ。意志力に頼らない設計に切り替えること。"
                            ),
                            "transition_hook": "では具体的にどう設計を変えるのか。",
                        },
                        {
                            "heading": "If-Thenプランニングの威力",
                            "body": (
                                "ピーター・ゴルヴィッツァーの研究では、'もしXが起きたらYをする'と事前に決めるだけで実行率が2〜3倍になった。"
                                "意志力ではなく、トリガーで体を動かす設計だ。"
                                "例: 朝ベッドから足が床についたら、コップ1杯の水を飲む。それだけで習慣が回り始める。"
                            ),
                            "transition_hook": "ここで多くの人が次の段階で躓く。",
                        },
                        {
                            "heading": "環境設計が最終防衛線になる",
                            "body": (
                                "BJ Foggが言うには、'良い行動は簡単に、悪い行動は難しく'すれば習慣は勝手に強化される。"
                                "スマホを別室に置く、運動着を玄関に置く、これだけで実行率は劇的に変わる。"
                                "意志ではなく構造で勝つ。それが続ける人の共通点だ。"
                            ),
                            "transition_hook": "",
                        },
                    ],
                    "outro": (
                        "意志力に頼ることは、燃料が漏れたタンクで走り続けるようなものだ。"
                        "あなたはダメじゃない。設計が悪いだけだ。"
                        "今日、たった1つ。トリガーと環境を1つ整えてほしい。それで明日が変わる。"
                    ),
                    "cta": "あなたが一番続かなかった習慣は何ですか?コメント欄で、トリガーになる行動とセットで書いてみてください。",
                    "approx_chars": 2400,
                    "approx_runtime_seconds": 600,
                },
                "en": {
                    "title": title_en,
                    "hook_5s": "Lacking motivation isn't your fault. It's a design flaw.",
                    "intro": (
                        "You decide 'today is the day,' and by evening it's gone. "
                        "That cycle makes you feel broken. The research says otherwise: the problem isn't you, it's your environment."
                    ),
                    "sections": [
                        {
                            "heading": "Willpower is fuel, not muscle",
                            "body": (
                                "Roy Baumeister's work showed willpower depletes through the day. "
                                "By evening, your decision quality drops. That's why 'study at night' rarely sticks. "
                                "The fix isn't more discipline. It's removing the need for it."
                            ),
                            "transition_hook": "So what does that look like in practice?",
                        },
                        {
                            "heading": "If-Then plans triple your follow-through",
                            "body": (
                                "Peter Gollwitzer found that pre-deciding 'if X happens, I do Y' boosted execution 2-3x. "
                                "You're not relying on motivation. You're relying on a trigger. "
                                "Example: 'When my feet hit the floor, I drink a glass of water.' That's it."
                            ),
                            "transition_hook": "Most people stop there. They shouldn't.",
                        },
                        {
                            "heading": "Design beats discipline",
                            "body": (
                                "BJ Fogg: make good behaviors easy, bad ones hard. "
                                "Phone in another room. Workout clothes by the door. "
                                "These tiny moves outperform any motivational speech."
                            ),
                            "transition_hook": "",
                        },
                    ],
                    "outro": (
                        "Relying on willpower is running on a leaking tank. "
                        "You aren't broken. The design is. "
                        "Pick one trigger today. Tomorrow looks different."
                    ),
                    "cta": "What habit have you tried hardest to keep? Drop it in the comments with the trigger you'll attach to it.",
                    "approx_words": 410,
                    "approx_runtime_seconds": 600,
                },
            },
            "shorts_jp": [
                {
                    "label": "shorts_jp_1",
                    "hook_7s": "やる気が出ないのは、あなたのせいじゃない。設計のせいだ。",
                    "main_35s": (
                        "意志力は朝から減り続ける有限資源。"
                        "だから「夜に勉強」は構造的に無理ゲー。"
                        "代わりに、'もしXが起きたらYをする'と事前に決めておく。"
                        "脳ではなくトリガーが体を動かす状態にする。"
                    ),
                    "cta_18s": "今日、1つだけトリガーを決めてみてほしい。それだけで明日が違う。",
                    "approx_chars": 180,
                },
                {
                    "label": "shorts_jp_2",
                    "hook_7s": "続く人と続かない人。違いは才能じゃない。",
                    "main_35s": (
                        "続く人は、意志ではなく環境で勝負している。"
                        "スマホを別室に置く、運動着を玄関に置く。"
                        "それだけで実行率は跳ね上がる。"
                        "良い行動は簡単に、悪い行動は難しく。これが鉄則だ。"
                    ),
                    "cta_18s": "あなたの環境を1箇所だけ変えてみよう。今日の夜、明日の朝が変わる。",
                    "approx_chars": 180,
                },
                {
                    "label": "shorts_jp_3",
                    "hook_7s": "気合いで頑張るのを、今日でやめよう。",
                    "main_35s": (
                        "気合いの限界はあなたが決めるのではなく、脳の燃料が決める。"
                        "燃料切れの状態で頑張るのは、空のタンクで走るようなもの。"
                        "むしろ、燃料を使わない設計に切り替えるのが本当の戦略だ。"
                    ),
                    "cta_18s": "頑張るのをやめると、不思議と進む。試してみて。",
                    "approx_chars": 175,
                },
            ],
            "shorts_en": [
                {
                    "label": "shorts_en_1",
                    "hook_7s": "Low motivation isn't your fault. It's a design flaw.",
                    "main_35s": (
                        "Willpower depletes during the day. "
                        "Decide 'if X happens, I do Y' in advance. "
                        "Now a trigger moves you, not your mood. "
                        "Example: feet on floor → water. Simple. Works."
                    ),
                    "cta_18s": "Pick one trigger today. Watch tomorrow change.",
                    "approx_words": 88,
                },
                {
                    "label": "shorts_en_2",
                    "hook_7s": "Consistent people don't have more discipline. They have better design.",
                    "main_35s": (
                        "Phone in another room. Gym clothes by the door. "
                        "Make good behavior easy, bad behavior hard. "
                        "That's the real lever."
                    ),
                    "cta_18s": "Change one thing in your environment tonight.",
                    "approx_words": 85,
                },
                {
                    "label": "shorts_en_3",
                    "hook_7s": "Stop trying to push through with willpower.",
                    "main_35s": (
                        "Your fuel runs out. Pushing harder on empty wastes you. "
                        "Real strategy: design out the need for willpower. "
                        "Systems beat discipline."
                    ),
                    "cta_18s": "Stop forcing it. Design it. Try it for a week.",
                    "approx_words": 80,
                },
            ],
            "ceo_brief": "(SIMULATION) 長尺は'問題は環境設計'という反直感的フックから3セクションで論証。Shortsは長尺の各セクションを独立スクリプト化、相互送客が可能な構成。",
            "chat_post": {
                "text": "@director 長尺JP/EN+Shorts3本/言語、計8脚本完了。全て同一サブテーマで構造的に揃えた。サムネ/タイトル詰めお願い。",
                "mentions": ["@director"],
                "kind": "handoff",
            },
        }
        return EmployeeResult(
            employee=self.JOB_TITLE,
            output=sim,
            model=f"{self.model} [SIM]",
            notes=["シミュレーションモード"],
        )
