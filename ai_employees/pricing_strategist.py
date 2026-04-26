"""価格戦略担当 ── 売上・在庫データを見て価格を最適化する。"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_employees.base import AIEmployee, EmployeeResult


class PricingStrategist(AIEmployee):
    JOB_TITLE = "価格戦略担当"
    HANDLE = "@pricing"

    SYSTEM_PROMPT = """あなたは「BeautyTech Lab」の価格戦略担当です。
日次の売上・在庫データを見て、各SKUの価格を最適化する責務を負います。
あなたの判断は即座にShopify上の価格更新CSVへ反映され、現場で実行されます。

【判断基準】
- 7日売上 0個 かつ 在庫 >= 15: 値下げ候補 (-10%)
- 7日売上 1〜2個 かつ 在庫 >= 10: 微調整 (-5%)
- 7日売上 5個以上 かつ 在庫 <= 5: 値上げ候補 (+5〜10%)
- それ以外: 据え置き
- 原価割れ(price < cost * 1.4)は絶対禁止
- compare_at_price は調整後の price * 1.3〜1.5 に再設定

【あなたの哲学】
- 値下げは弱気の表れではなく、データドリブンな在庫循環施策
- 値上げは「売れているのに在庫薄」のときだけ。客単価UPのチャンスを逃さない
- 同一SKUを連続して動かさない。前日にも触っていれば「hold」を推奨

【出力スキーマ】
{
  "decisions": [
    {
      "sku": "BTL-XXX-JP",
      "current_price": 整数,
      "new_price": 整数,
      "compare_at_price": 整数,
      "action": "discount|raise|hold",
      "reason": "1文の理由 (日本語)",
      "discount_pct": -10〜+10
    }
  ],
  "summary": "今日の価格調整サマリー (3文以内・日本語)",
  "chat_post": {
    "text": "値付け判断のチャット発言 (120字以内・@cfo にメンション、根拠が薄い案には @merchandiser に concern を返してもよい)",
    "mentions": ["@cfo"],
    "kind": "message"
  }
}

数値は数値型で出すこと。"""

    def run(
        self,
        sales_snapshot: list[dict[str, Any]],
        out_dir: str = "data/csv_out",
        workspace=None,
    ) -> EmployeeResult:
        ctx = workspace.context_for(self.HANDLE) if workspace else ""
        prompt = (
            "本日の売上・在庫スナップショットを以下に共有します。"
            "上記ルールに従って各SKUの価格判断を出してください。\n\n"
            f"```json\n{json.dumps(sales_snapshot, ensure_ascii=False)}\n```\n\n"
            f"【ワークスペース・コンテキスト】\n{ctx}"
        )
        result = self._ask(prompt, max_tokens=4000)

        # update.py が読めるCSV形式 (sku, price, compare_at_price)
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        date = datetime.now().strftime("%Y-%m-%d")
        path = Path(out_dir) / f"{date}_price_update.csv"
        decisions = [
            d for d in result.output.get("decisions", [])
            if d.get("action") in ("discount", "raise")
        ]
        if decisions:
            with path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["sku", "price", "compare_at_price"]
                )
                writer.writeheader()
                for d in decisions:
                    writer.writerow({
                        "sku": d["sku"],
                        "price": d["new_price"],
                        "compare_at_price": d["compare_at_price"],
                    })
            result.notes.append(f"価格更新CSV: {path} ({len(decisions)}件)")
        else:
            result.notes.append("価格調整対象なし(全SKU据え置き)")
        if workspace is not None:
            self._post_chat_from_output(workspace, result.output)
        return result

    def _simulated_response(self, user_prompt: str) -> EmployeeResult:
        import re
        m = re.search(r"```json\s*(\[.*?\])\s*```", user_prompt, re.DOTALL)
        snap = json.loads(m.group(1)) if m else []

        decisions = []
        for s in snap:
            sku = s.get("sku", "UNK")
            price = int(s.get("price", 0))
            cost = int(s.get("cost", price // 4))
            sold7 = int(s.get("sold_last_7days", 0))
            stock = int(s.get("inventory", 0))
            floor = int(cost * 1.4)

            if sold7 == 0 and stock >= 15:
                new_price = max(int(price * 0.9), floor)
                action, pct, reason = "discount", -10, "7日間販売ゼロかつ在庫過多のため値下げ"
            elif sold7 <= 2 and stock >= 10:
                new_price = max(int(price * 0.95), floor)
                action, pct, reason = "discount", -5, "売上低迷のため微調整"
            elif sold7 >= 5 and stock <= 5:
                new_price = int(price * 1.07)
                action, pct, reason = "raise", 7, "好調かつ在庫薄のため値上げで利益最大化"
            else:
                new_price = price
                action, pct, reason = "hold", 0, "現状維持"

            decisions.append({
                "sku": sku,
                "current_price": price,
                "new_price": new_price,
                "compare_at_price": int(new_price * 1.4),
                "action": action,
                "reason": reason,
                "discount_pct": pct,
            })

        n_change = sum(1 for d in decisions if d["action"] != "hold")
        sim = {
            "decisions": decisions,
            "summary": f"(SIMULATION) {n_change}件の価格調整を提案。残りは据え置き。",
            "chat_post": {
                "text": f"@cfo 価格判断完了: 調整{n_change}件・据置{len(decisions)-n_change}件。原価割れなし、ルール通り。",
                "mentions": ["@cfo"],
                "kind": "message",
            },
        }
        return EmployeeResult(
            employee=self.JOB_TITLE,
            output=sim,
            model=f"{self.model} [SIM]",
            notes=["シミュレーションモード"],
        )
