"""CFO ── コンテンツ収益・再生指標を集計し、オーナーへの3行レポートを生成する。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_employees.base import AIEmployee, EmployeeResult


class CFO(AIEmployee):
    JOB_TITLE = "CFO"
    HANDLE = "@cfo"

    SYSTEM_PROMPT = """あなたは「ContentLab Tokyo」のCFOです。
オーナーは超多忙のため、あなたが書く日次レポートに人生の意思決定の一部を委ねています。
冗長な報告は信用を失います。短く、鋭く、判断材料になる情報だけを出してください。

【観察すべき指標 (動画ビジネス)】
- 投下: 本日生産した動画本数 (long/shorts別)
- 配信: 本日YouTube/TikTokに投稿した本数
- 再生: 24h総再生数・平均視聴維持率
- 収益: 本日広告収益(USD/JPY)・推定RPM
- 登録者増減
- ファネル: top videos / underperformers
- ランウェイ: API+編集費の月次予算消化と残予算

【オーナーへの日次レポート構造】
- 1行目: 数字のヘッドライン (再生・収益・登録)
- 2行目: 良いニュース or 警告 (1個だけ)
- 3行目: 明日の打ち手 (動詞始まり・1個だけ)

【哲学】
- 「絶好調です!」のような感情報告は禁止。数字で語る
- 悪い数字こそ最初に出す。隠蔽は最大の罪
- オーナーの読了時間は10秒。それ以上のレポートは存在しないのと同じ

【出力スキーマ】
{
  "report_date": "YYYY-MM-DD",
  "headline": "1行目 (50字以内)",
  "highlight_or_warning": "2行目 (60字以内)",
  "next_action": "3行目 (60字以内、動詞始まり)",
  "kpis": {
    "videos_produced_today": 整数,
    "videos_posted_today": 整数,
    "views_24h": 整数,
    "avg_retention_pct": 数値,
    "ad_revenue_jpy": 整数,
    "estimated_rpm_jpy": 数値,
    "subs_delta": 整数,
    "api_spend_jpy": 整数,
    "monthly_budget_remaining_jpy": 整数
  },
  "top_videos": ["video_label1", "..."],
  "underperformers": ["video_label1", "..."],
  "chat_post": {
    "text": "チームへの財務発言 (120字以内、必要なら @ceo にエスカレ)",
    "mentions": [],
    "kind": "message"
  }
}"""

    def run(
        self,
        business_state: dict[str, Any],
        out_dir: str = "data/reports",
        workspace=None,
    ) -> EmployeeResult:
        ctx = workspace.context_for(self.HANDLE) if workspace else ""
        prompt = (
            "本日の経営データを共有します。スキーマに沿った日次レポートを出してください。\n\n"
            f"```json\n{json.dumps(business_state, ensure_ascii=False)}\n```\n\n"
            f"【ワークスペース・コンテキスト】\n{ctx}"
        )
        result = self._ask(prompt, max_tokens=2000)

        Path(out_dir).mkdir(parents=True, exist_ok=True)
        date = datetime.now().strftime("%Y-%m-%d")
        path = Path(out_dir) / f"{date}_report.json"
        path.write_text(
            json.dumps(result.output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result.notes.append(f"レポート保存: {path}")
        if workspace is not None:
            self._post_chat_from_output(workspace, result.output)
        return result

    def _simulated_response(self, user_prompt: str) -> EmployeeResult:
        import re
        m = re.search(r"```json\s*(\{.*?\})\s*```", user_prompt, re.DOTALL)
        state = json.loads(m.group(1)) if m else {}

        produced = int(state.get("videos_produced_today", 8))
        posted = int(state.get("videos_posted_today", 0))
        views = int(state.get("views_24h", 0))
        ret = float(state.get("avg_retention_pct", 0))
        ad_rev = int(state.get("ad_revenue_jpy", 0))
        rpm = float(state.get("estimated_rpm_jpy", 0))
        subs = int(state.get("subs_delta", 0))
        api_spend = int(state.get("api_spend_jpy", 0))
        budget_remain = int(state.get("monthly_budget_remaining_jpy", 100000 - api_spend))

        if posted == 0 and produced > 0:
            headline = f"本日生産: {produced}本 (long2 / shorts6) / 投稿0本"
            warn = "脚本完了・編集待ち。投稿パイプライン未稼働"
            action = "編集者に最初の長尺マスターを渡す"
        elif posted == 0 and produced == 0:
            headline = "本日生産0本 / 投稿0本"
            warn = "稼働初日。供給ライン未点火"
            action = "research → script → direct を回し制作開始する"
        else:
            headline = f"投稿{posted}本 / 24h {views:,} 再生 / 登録者+{subs}"
            warn = f"平均維持率{ret}% / 推定RPM ¥{rpm}"
            action = "上位2本のフックをShortsに横展開する"

        sim = {
            "report_date": datetime.now().strftime("%Y-%m-%d"),
            "headline": headline,
            "highlight_or_warning": warn,
            "next_action": action,
            "kpis": {
                "videos_produced_today": produced,
                "videos_posted_today": posted,
                "views_24h": views,
                "avg_retention_pct": ret,
                "ad_revenue_jpy": ad_rev,
                "estimated_rpm_jpy": rpm,
                "subs_delta": subs,
                "api_spend_jpy": api_spend,
                "monthly_budget_remaining_jpy": budget_remain,
            },
            "top_videos": state.get("top_videos", []),
            "underperformers": state.get("underperformers", []),
            "chat_post": {
                "text": f"本日: {headline}。{warn}。",
                "mentions": ["@ceo"] if posted == 0 else [],
                "kind": "message",
            },
        }
        return EmployeeResult(
            employee=self.JOB_TITLE,
            output=sim,
            model=f"{self.model} [SIM]",
            notes=["シミュレーションモード"],
        )
