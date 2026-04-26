"""AI従業員の共通基盤。

全従業員はこの`AIEmployee`を継承する。Claude APIへのアクセス、
プロンプトキャッシュ、JSON出力パース、トークン使用量集計を一元管理する。

設計原則 (CEO Jobs):
  1. システムプロンプトは必ずキャッシュ対象 (cache_control=ephemeral)
  2. 出力はJSONを強制 (構造化データのみ受け取る)
  3. シミュレーションモードではClaude APIを呼ばずスタブ応答を返す
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.logger import setup_logger

logger = setup_logger(__name__)

# 月次APIコスト予算 (円)。超過すると新規API呼び出しを拒否する
COST_LEDGER_PATH = Path("data/cost_ledger.jsonl")
DEFAULT_MONTHLY_BUDGET_JPY = 10_000  # config/business.yaml の budget_allocation.api_and_ops_jpy 既定値


def _read_monthly_cost_jpy(path: Path = COST_LEDGER_PATH) -> float:
    """当月使用済みのAPIコスト合計 (円)。"""
    if not path.exists():
        return 0.0
    ym = datetime.now().strftime("%Y-%m")
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("ts", "").startswith(ym):
            total += float(row.get("cost_jpy", 0))
    return round(total, 2)


def _append_ledger(entry: dict[str, Any], path: Path = COST_LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class BudgetExceededError(RuntimeError):
    """月次API予算を超過した場合に投げる。CEOが運用を一時停止できる。"""


@dataclass
class EmployeeResult:
    """AI従業員1回の業務結果。"""

    employee: str
    output: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model: str = ""
    notes: list[str] = field(default_factory=list)

    def cost_jpy_estimate(self) -> float:
        """ざっくりとしたAPIコスト試算 (円)。

        概算レート (1USD≒155円, 2026/04時点):
          Sonnet: $3 / Mtok input, $15 / Mtok output, cache read $0.30
          Haiku:  $1 / Mtok input, $5  / Mtok output, cache read $0.10
        モデル名で簡易判定する。
        """
        is_haiku = "haiku" in self.model
        in_rate = 1.0 if is_haiku else 3.0
        out_rate = 5.0 if is_haiku else 15.0
        cache_rate = 0.1 if is_haiku else 0.3
        usd = (
            self.input_tokens * in_rate
            + self.output_tokens * out_rate
            + self.cache_read_tokens * cache_rate
            + self.cache_write_tokens * (in_rate * 1.25)
        ) / 1_000_000
        return round(usd * 155.0, 2)


COWORK_PROTOCOL = """
【コワーキング規約 (全AI従業員共通)】
あなたは一人で働いているのではない。同じワークスペースに同僚AIがいる。
仕事の前にコンテキスト(ホワイトボード・あなた宛のinbox・直近のチームチャット)を必ず読む。
仕事を終えたら必ず1メッセージをチームチャットに残すこと。

メッセージ作法:
- 端的に。1〜3文。冗長な丁寧語は不要。
- 同僚に振る作業は @<handle> でメンション (@ceo, @researcher, @merchandiser, @pricing, @cfo)
- 引き継ぎは kind="handoff"、懸念は "concern"、雑談は "message"
- 上司にも遠慮なく異論を出してよい。ただし根拠を添える。

各従業員の出力JSONには必ず以下のフィールドを含める:
  "chat_post": {
    "text": "チャットへの投稿本文",
    "mentions": ["@ceo", "@merchandiser"] や [],
    "kind": "message" | "handoff" | "concern" | "standup" | "sign_off"
  }
"""


class AIEmployee:
    """AI従業員の基底クラス。

    継承クラスは下記をオーバーライドする:
      - JOB_TITLE: 役職名 (ログ用)
      - HANDLE: チャット内ハンドル (@xxx 形式)
      - SYSTEM_PROMPT: 役割定義 (1024トークン以上推奨。キャッシュされる)
      - run(...): 業務実行ロジック
    """

    JOB_TITLE: str = "AI従業員"
    HANDLE: str = "@employee"
    SYSTEM_PROMPT: str = "あなたはAI従業員です。"

    def __init__(
        self,
        model: str,
        simulation_mode: bool = False,
        monthly_budget_jpy: float = DEFAULT_MONTHLY_BUDGET_JPY,
    ):
        self.model = model
        self.simulation_mode = simulation_mode
        self.monthly_budget_jpy = monthly_budget_jpy
        self._client = None
        if not simulation_mode:
            try:
                from anthropic import Anthropic
            except ImportError as e:
                raise RuntimeError(
                    "anthropic SDKがインストールされていません。"
                    "pip install -r requirements.txt を実行してください。"
                ) from e
            api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEYが.envに設定されていません。"
                    "シミュレーションのみで動かす場合は config/business.yaml の "
                    "operations.simulation_mode: true にしてください。"
                )
            self._client = Anthropic(api_key=api_key)

    # ------------------------------------------------------------------ #
    # 共通: Claude API呼び出し
    # ------------------------------------------------------------------ #

    def _ask(
        self,
        user_prompt: str,
        max_tokens: int = 4096,
        json_only: bool = True,
    ) -> EmployeeResult:
        """Claude APIに問い合わせ、JSON応答をパースして返す。"""
        if self.simulation_mode:
            return self._simulated_response(user_prompt)

        # 予算ガード: 月次予算を超過していたら新規API呼び出しを拒否
        used = _read_monthly_cost_jpy()
        if used >= self.monthly_budget_jpy:
            raise BudgetExceededError(
                f"月次API予算超過: ¥{used:,.0f} / ¥{self.monthly_budget_jpy:,.0f}。"
                f"config/business.yaml の budget_allocation.api_and_ops_jpy を上げるか、"
                f"data/cost_ledger.jsonl を翌月1日に空にしてください。"
            )

        # システムプロンプトはキャッシュ対象 (役職定義 + 共通コワーク規約)
        system_blocks = [
            {
                "type": "text",
                "text": self.SYSTEM_PROMPT + "\n\n" + COWORK_PROTOCOL,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        msg_user = user_prompt
        if json_only:
            msg_user += (
                "\n\n出力は厳密に有効なJSONオブジェクトのみ。"
                "前置き・コードフェンス・説明文は一切禁止。"
            )

        logger.info(f"[{self.JOB_TITLE}] Claude API呼び出し開始 (model={self.model})")
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": msg_user}],
        )

        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        usage = resp.usage
        result = EmployeeResult(
            employee=self.JOB_TITLE,
            output=self._parse_json(text) if json_only else {"text": text},
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            model=self.model,
        )
        cost = result.cost_jpy_estimate()
        _append_ledger({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "employee": self.JOB_TITLE,
            "model": self.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cache_read_tokens": result.cache_read_tokens,
            "cache_write_tokens": result.cache_write_tokens,
            "cost_jpy": cost,
        })
        logger.info(
            f"[{self.JOB_TITLE}] 完了 "
            f"(in={result.input_tokens}, out={result.output_tokens}, "
            f"cache_read={result.cache_read_tokens}, ¥{cost})"
        )
        return result

    # ------------------------------------------------------------------ #
    # JSONパース
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """LLM出力からJSONを取り出す (コードフェンス混入にも耐える)。"""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 最初の{...}を貪欲に拾う最後の手段
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                return json.loads(m.group(0))
            raise

    # ------------------------------------------------------------------ #
    # コワーク: チャット投稿ヘルパー
    # ------------------------------------------------------------------ #

    def _post_chat_from_output(self, workspace, output: dict[str, Any]) -> None:
        """LLM出力に含まれる chat_post を実際のチャットに反映する。"""
        cp = output.get("chat_post") or {}
        text = (cp.get("text") or "").strip()
        if not text:
            return
        workspace.post(
            sender=self.HANDLE,
            text=text,
            mentions=cp.get("mentions") or [],
            kind=cp.get("kind") or "message",
        )

    # ------------------------------------------------------------------ #
    # シミュレーション応答 (継承先で具体化)
    # ------------------------------------------------------------------ #

    def _simulated_response(self, user_prompt: str) -> EmployeeResult:
        """API契約前/オフライン時のスタブ応答。継承先で意味のあるダミーを返す。"""
        return EmployeeResult(
            employee=self.JOB_TITLE,
            output={"simulated": True, "message": "(simulation mode)"},
            model=f"{self.model} [SIM]",
            notes=["シミュレーションモードのため固定応答"],
        )
