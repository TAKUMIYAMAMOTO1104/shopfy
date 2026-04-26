"""共有ワークスペース ── AI従業員が会話・引き継ぎ・指摘し合うための器。

設計:
  - chat_log.jsonl  : 全発言の単一ソース・オブ・トゥルース (JSON Lines)
  - inbox/<handle>.jsonl : メンション付きメッセージの受信箱
  - whiteboard.md   : 今日の議題・決定事項 (人間も読む)
  - daily_log/<date>.jsonl : 1日の会話ログをスナップショット保存
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class Workspace:
    """AIチームのSlack的シェアドスペース。"""

    def __init__(self, root: str | Path = "data/cowork"):
        self.root = Path(root)
        self.chat_log = self.root / "chat_log.jsonl"
        self.whiteboard = self.root / "whiteboard.md"
        self.inbox_dir = self.root / "inbox"
        self.daily_dir = self.root / "daily_log"
        for p in (self.root, self.inbox_dir, self.daily_dir):
            p.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 投稿 / 受信
    # ------------------------------------------------------------------ #

    def post(
        self,
        sender: str,
        text: str,
        mentions: list[str] | None = None,
        kind: str = "message",
    ) -> dict[str, Any]:
        """チャットに投稿する。mentionsがあれば各受信者のinboxにも複写。"""
        msg = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "from": sender,
            "to": mentions or [],
            "kind": kind,  # standup | message | handoff | concern | sign_off
            "text": text,
        }
        with self.chat_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        # 当日ログにもコピー
        daily = self.daily_dir / f"{datetime.now():%Y-%m-%d}.jsonl"
        with daily.open("a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        # メンション → inbox
        for handle in (mentions or []):
            inbox_path = self.inbox_dir / f"{handle.lstrip('@')}.jsonl"
            with inbox_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        return msg

    def read_inbox(self, recipient: str, mark_read: bool = True) -> list[dict]:
        """指定された受信者のinboxを読む。デフォルトでは読み終わったらクリアする。"""
        path = self.inbox_dir / f"{recipient.lstrip('@')}.jsonl"
        if not path.exists():
            return []
        msgs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if mark_read:
            path.unlink()
        return msgs

    def recent_chat(self, n: int = 30) -> list[dict]:
        """直近n件のチャット履歴。"""
        if not self.chat_log.exists():
            return []
        lines = self.chat_log.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(line) for line in lines if line.strip()]

    def today_chat(self) -> list[dict]:
        """本日のチャット履歴。"""
        path = self.daily_dir / f"{datetime.now():%Y-%m-%d}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # ------------------------------------------------------------------ #
    # ホワイトボード
    # ------------------------------------------------------------------ #

    def set_theme(self, theme: str) -> None:
        """本日のテーマをホワイトボードに掲示。"""
        date = datetime.now().strftime("%Y-%m-%d")
        self.whiteboard.write_text(
            f"# 本日のテーマ ({date})\n\n{theme}\n", encoding="utf-8"
        )

    def read_whiteboard(self) -> str:
        return self.whiteboard.read_text(encoding="utf-8") if self.whiteboard.exists() else ""

    # ------------------------------------------------------------------ #
    # コンテキスト整形 (LLMに渡すプロンプト断片)
    # ------------------------------------------------------------------ #

    def context_for(self, handle: str, recent_n: int = 20) -> str:
        """LLMにそのまま埋め込めるコンテキスト文字列を生成。"""
        wb = self.read_whiteboard().strip()
        inbox = self.read_inbox(handle, mark_read=False)
        chat = self.recent_chat(recent_n)

        parts: list[str] = []
        if wb:
            parts.append(f"【ホワイトボード】\n{wb}")
        if inbox:
            parts.append("【あなた宛のメッセージ (inbox)】")
            for m in inbox:
                parts.append(f"  [{m['ts']}] {m['from']} → あなた: {m['text']}")
        if chat:
            parts.append("【直近のチームチャット】")
            for m in chat:
                arrow = f" → {','.join(m['to'])}" if m["to"] else ""
                parts.append(f"  [{m['ts']}] {m['from']}{arrow} ({m['kind']}): {m['text']}")
        return "\n".join(parts) if parts else "(まだ会話なし)"

    # ------------------------------------------------------------------ #
    # 表示・リセット
    # ------------------------------------------------------------------ #

    def reset_today(self) -> None:
        """その日のログ・inboxをクリア (新しいサイクル開始時用)。"""
        for f in self.inbox_dir.glob("*.jsonl"):
            f.unlink()
        daily = self.daily_dir / f"{datetime.now():%Y-%m-%d}.jsonl"
        if daily.exists():
            daily.unlink()
