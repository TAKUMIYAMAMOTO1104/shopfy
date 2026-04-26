"""CFO ── 経営数値を集計し、オーナーへの3行レポートを生成する。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_employees.base import AIEmployee, EmployeeResult


class CFO(AIEmployee):
    JOB_TITLE = "CFO"
    HANDLE = "@cfo"

    SYSTEM_PROMPT = """あなたは「BeautyTech Lab」のCFOです。
オーナー(ビジネスオーナー)は超多忙のため、あなたが書く日次レポートに人生の意思決定の一部を委ねています。
冗長な報告は信用を失います。短く、鋭く、判断材料になる情報だけを出してください。

【オーナーへの日次レポート構造】
- 1行目: 売上・粗利のヘッドライン (絵文字なし)
- 2行目: 良いニュース or 警告 (1個だけ)
- 3行目: 明日の打ち手 (1個だけ・実行可能な動詞で始める)
- 加えて重要KPI(数値のみ)を構造化して残す

【観察すべき指標】
- 売上 (revenue_jpy)
- 粗利 (gross_profit_jpy)
- 粗利率 (gross_margin_pct)
- 広告費消化 (ad_spend_jpy_today / monthly_budget_jpy)
- 在庫評価額 (inventory_value_jpy)
- 売れ筋TOP3 / 不振TOP3
- キャッシュランウェイ (現預金 / 月次バーンレート)

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
    "revenue_jpy": 整数,
    "gross_profit_jpy": 整数,
    "gross_margin_pct": 数値,
    "ad_spend_jpy_today": 整数,
    "ad_budget_remaining_jpy": 整数,
    "inventory_value_jpy": 整数,
    "cash_runway_days": 数値
  },
  "top_sellers": ["SKU1", "SKU2", "SKU3"],
  "underperformers": ["SKU1", "SKU2", "SKU3"],
  "chat_post": {
    "text": "今日のチームへの財務サマリー発言 (120字以内、必要なら @ceo にエスカレ)",
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

        revenue = int(state.get("revenue_jpy", 0))
        cost = int(state.get("cogs_jpy", 0))
        gp = revenue - cost
        margin = round(gp / revenue * 100, 1) if revenue else 0.0
        ad_today = int(state.get("ad_spend_jpy_today", 2000))
        ad_budget_remaining = int(state.get("ad_budget_remaining_jpy", 60000 - ad_today))
        inventory = int(state.get("inventory_value_jpy", 30000))
        cash = int(state.get("cash_jpy", 100000))
        burn = int(state.get("daily_burn_jpy", 3500))
        runway = round(cash / burn, 1) if burn else 999

        if revenue == 0:
            headline = f"売上0円 / 粗利0円 / 在庫¥{inventory:,}"
            warn = "稼働初日。まだ受注なし、これは正常"
            action = "出品CSVをShopifyに投入し、広告配信を開始する"
        else:
            headline = f"売上¥{revenue:,} / 粗利¥{gp:,} ({margin}%)"
            warn = f"広告残予算¥{ad_budget_remaining:,}・キャッシュランウェイ{runway}日"
            action = "売れ筋SKUの在庫を上限まで確保する"

        sim = {
            "report_date": datetime.now().strftime("%Y-%m-%d"),
            "headline": headline,
            "highlight_or_warning": warn,
            "next_action": action,
            "kpis": {
                "revenue_jpy": revenue,
                "gross_profit_jpy": gp,
                "gross_margin_pct": margin,
                "ad_spend_jpy_today": ad_today,
                "ad_budget_remaining_jpy": ad_budget_remaining,
                "inventory_value_jpy": inventory,
                "cash_runway_days": runway,
            },
            "top_sellers": state.get("top_sellers", []),
            "underperformers": state.get("underperformers", []),
            "chat_post": {
                "text": f"本日: {headline}。{warn}。",
                "mentions": ["@ceo"] if revenue == 0 else [],
                "kind": "message",
            },
        }
        return EmployeeResult(
            employee=self.JOB_TITLE,
            output=sim,
            model=f"{self.model} [SIM]",
            notes=["シミュレーションモード"],
        )
