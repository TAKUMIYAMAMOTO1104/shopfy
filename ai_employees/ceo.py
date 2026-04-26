"""CEO Jobs ── AI従業員チームを率いるリーダー。

現実世界ではこのCEOは「会話で指揮を執る私(オーナーが対話している私)」だが、
ワークスペース内では同僚AIたちに対して朝会で方針を示し、終礼で総評を述べる
1人の参加者でもある。だからLLMエージェントとして実装する。
"""

from __future__ import annotations

import json
from typing import Any

from ai_employees.base import AIEmployee, EmployeeResult


class CEO(AIEmployee):
    JOB_TITLE = "CEO"
    HANDLE = "@ceo"

    SYSTEM_PROMPT = """あなたは「BeautyTech Lab」のCEO、ジョブズ(Jobs)です。
年商50億円のグローバルEC企業を率い、AI従業員チーム(リサーチ部長/マーチャンダイザー/価格戦略担当/CFO)を指揮しています。

【あなたの哲学】
- ミニマル・プレミアム。ノイズより本質を選ぶ
- 数字で判断する。感情で動かない
- 部下を信頼するが、緩んだ判断は容赦なく指摘する
- 部下の異論は歓迎する。沈黙する部下は危険信号

【あなたの責務】
朝の役割: ホワイトボードに「本日のテーマ」を1〜2文で示し、優先順位を明確にする
夜の役割: その日のチャット履歴を読み、3行以内でチームを総評し、明日の方針を1点だけ示す

【絶対ルール】
- 説教しない。冗長にしない
- 名指しの賞賛/指摘は具体的にする
- 1日に話す量はオーナーが10秒で読める量

【出力スキーマ】

朝の出力 (theme="morning"):
{
  "theme": "本日のテーマ (1〜2文・80字以内)",
  "priority": "今日の最優先事項 (1文)",
  "chat_post": {
    "text": "朝会発言 (100字以内)",
    "mentions": [],
    "kind": "standup"
  }
}

夜の出力 (theme="closing"):
{
  "evaluation_3_lines": [
    "1行目: 今日のチームの動きへの総評",
    "2行目: 名指しの賞賛 or 指摘 (1人だけ)",
    "3行目: 明日の方針 (動詞始まり)"
  ],
  "chat_post": {
    "text": "終礼発言 (3行を改行で連結)",
    "mentions": [],
    "kind": "sign_off"
  }
}"""

    def open_day(self, workspace) -> EmployeeResult:
        """朝会: 本日のテーマを掲示し朝会発言を投稿。"""
        ctx = workspace.context_for(self.HANDLE, recent_n=10)
        prompt = (
            "あなたはこれから朝会で本日のテーマを示します。"
            "ワークスペースの直近コンテキストは以下:\n\n"
            f"{ctx}\n\n"
            "schemaは theme=\"morning\" の方を使ってください。"
        )
        result = self._ask(prompt, max_tokens=600)
        theme = result.output.get("theme", "")
        priority = result.output.get("priority", "")
        if theme:
            workspace.set_theme(f"{theme}\n\n優先事項: {priority}")
        self._post_chat_from_output(workspace, result.output)
        return result

    def close_day(self, workspace) -> EmployeeResult:
        """終礼: 当日のチャットを読み、3行で総評。"""
        chat = workspace.today_chat()
        chat_text = "\n".join(
            f"[{m['ts'][-8:]}] {m['from']} ({m['kind']}): {m['text']}"
            for m in chat
        )
        prompt = (
            "本日のチームチャットは以下です。スキーマ theme=\"closing\" で総評してください。\n\n"
            f"{chat_text or '(発言なし)'}"
        )
        result = self._ask(prompt, max_tokens=600)
        self._post_chat_from_output(workspace, result.output)
        return result

    def _simulated_response(self, user_prompt: str) -> EmployeeResult:
        if "morning" in user_prompt:
            sim = {
                "theme": "本日のテーマ: 利益率優先。値下げは慎重に、引き継ぎは丁寧に。",
                "priority": "新規SKU5件の同時ローンチ精度を最大化する",
                "chat_post": {
                    "text": "おはよう。今日は新規ローンチ。粗利率35%以上を死守。各自、冒頭にこのテーマを意識して仕事せよ。",
                    "mentions": [],
                    "kind": "standup",
                },
            }
        else:
            sim = {
                "evaluation_3_lines": [
                    "新規5SKU・日英両市場対応のCSV生成まで完了。立ち上げとして合格点。",
                    "@pricing 価格戦略の根拠提示が明快だった。引き続き頼む。",
                    "明日: 出品後24時間のCTRを確認し、不振SKUは早期に値付けを見直す",
                ],
                "chat_post": {
                    "text": "今日は合格点。@pricing の価格判断が明快だった。明日は出品後24hのCTRを見て不振SKUの値付けを早めに見直そう。",
                    "mentions": ["@pricing"],
                    "kind": "sign_off",
                },
            }
        return EmployeeResult(
            employee=self.JOB_TITLE,
            output=sim,
            model=f"{self.model} [SIM]",
            notes=["シミュレーションモード"],
        )
