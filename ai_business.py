#!/usr/bin/env python3
"""AI自律型ECビジネス・コマンドラインツール (コワーキング版)。

オーナーが叩く窓口。CEO Jobs と AI従業員4名が共有チャットで会話・引き継ぎ・
指摘し合いながら1日分の経営サイクルを自走する。

使い方:
  python ai_business.py init           # ビジネス状態を初期化
  python ai_business.py research       # リサーチ部長に商品候補を出させる
  python ai_business.py merchandise    # マーチャンダイザーにCSVを作らせる
  python ai_business.py price          # 価格戦略担当に値付けさせる
  python ai_business.py report         # CFOに日次レポートを書かせる
  python ai_business.py run-day        # 朝会→各業務→終礼の全ターンを実行
  python ai_business.py chat           # 本日の社内チャットをSlack風に表示
  python ai_business.py status         # 現在のビジネス状態を表示

設定ファイル: config/business.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ai_employees import CEO, CFO, Merchandiser, PricingStrategist, Researcher, Workspace
from utils.logger import setup_logger

load_dotenv()
logger = setup_logger("ai_business")

CONFIG_PATH = Path("config/business.yaml")


# ====================================================================== #
# 設定 & 状態
# ====================================================================== #

def load_config() -> dict[str, Any]:
    """YAMLが使えれば使い、なければ最小限のフォールバックパーサで読む。"""
    if not CONFIG_PATH.exists():
        logger.error(f"設定ファイルが見つかりません: {CONFIG_PATH}")
        sys.exit(1)
    try:
        import yaml  # type: ignore
        with CONFIG_PATH.open(encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        logger.warning("PyYAMLが未インストール。簡易パーサで読み込みます。")
        return _minimal_yaml_parse(CONFIG_PATH.read_text(encoding="utf-8"))


def _minimal_yaml_parse(text: str) -> dict[str, Any]:
    """ネスト2階層・スカラー・リストのみ対応のごく簡易なYAMLパーサ。"""
    out: dict[str, Any] = {}
    stack: list[tuple[int, dict | list]] = [(-1, out)]

    def _coerce(v: str) -> Any:
        v = v.strip()
        if v.startswith('"') and v.endswith('"'):
            return v[1:-1]
        if v == "true": return True
        if v == "false": return False
        try:
            if "." in v: return float(v)
            return int(v)
        except ValueError:
            return v

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1] if stack else out

        if stripped.startswith("- "):
            val = _coerce(stripped[2:])
            if not isinstance(parent, list):
                # 親辞書の最後のキーをリスト化
                last_key = list(parent.keys())[-1]
                if not isinstance(parent[last_key], list):
                    parent[last_key] = []
                parent[last_key].append(val)
            else:
                parent.append(val)
        elif ":" in stripped:
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip()
            if v == "":
                new: dict[str, Any] = {}
                parent[k] = new
                stack.append((indent, new))
            else:
                parent[k] = _coerce(v)

    return out


def load_state(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "initialized_at": None,
        "cash_jpy": 100000,
        "monthly_budget_jpy": 100000,
        "ad_spend_jpy_total": 0,
        "ad_spend_jpy_today": 0,
        "ad_budget_remaining_jpy": 60000,
        "revenue_jpy": 0,
        "cogs_jpy": 0,
        "inventory_value_jpy": 0,
        "daily_burn_jpy": 3500,
        "skus": [],
        "top_sellers": [],
        "underperformers": [],
    }


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ====================================================================== #
# 各従業員の起動ヘルパー
# ====================================================================== #

def _make_employee(cfg: dict, role_key: str, sim: bool):
    role = cfg["employees"][role_key]
    cls_map = {
        "researcher": Researcher,
        "merchandiser": Merchandiser,
        "pricing_strategist": PricingStrategist,
        "cfo": CFO,
        "ceo": CEO,
    }
    return cls_map[role_key](model=role["model"], simulation_mode=sim)


def _make_workspace(cfg: dict) -> Workspace:
    root = cfg.get("operations", {}).get("cowork_dir", "data/cowork")
    return Workspace(root=root)


# Slack風表示用の色付け (端末対応)
HANDLE_COLORS = {
    "@ceo":          "\033[1;33m",   # bold yellow
    "@researcher":   "\033[36m",     # cyan
    "@merchandiser": "\033[32m",     # green
    "@pricing":      "\033[35m",     # magenta
    "@cfo":          "\033[34m",     # blue
}
RESET = "\033[0m"


def _print_chat(messages: list[dict]) -> None:
    if not messages:
        print("(まだ発言なし)")
        return
    for m in messages:
        color = HANDLE_COLORS.get(m["from"], "")
        ts = m["ts"][-8:]
        kind_tag = f"[{m['kind']}]"
        mentions = " ".join(m["to"]) if m["to"] else ""
        print(f"  {ts} {color}{m['from']:14}{RESET} {kind_tag:11} {mentions:20} {m['text']}")


def _print_result(label: str, result) -> None:
    print(f"\n━━━━ {label} ({result.employee} / {result.model}) ━━━━")
    summary_keys = ["ceo_brief", "summary", "headline", "next_action", "top_pick_code"]
    for k in summary_keys:
        if k in result.output:
            print(f"  {k}: {result.output[k]}")
    for note in result.notes:
        print(f"  ・{note}")
    if result.input_tokens or result.output_tokens:
        print(
            f"  [tok in/out/cache_r: "
            f"{result.input_tokens}/{result.output_tokens}/{result.cache_read_tokens}, "
            f"≒¥{result.cost_jpy_estimate()}]"
        )


# ====================================================================== #
# サブコマンド
# ====================================================================== #

def cmd_init(args, cfg):
    state_path = Path(cfg["operations"]["state_file"])
    if state_path.exists() and not args.force:
        print(f"既に初期化済みです: {state_path} (再初期化は --force)")
        return
    state = load_state(state_path)
    state["initialized_at"] = datetime.now().isoformat(timespec="seconds")
    state["cash_jpy"] = cfg["business"]["budget_jpy_monthly"]
    state["monthly_budget_jpy"] = cfg["business"]["budget_jpy_monthly"]
    state["ad_budget_remaining_jpy"] = cfg["budget_allocation"]["ads_jpy"]
    save_state(state_path, state)
    print(f"\n✓ ビジネス '{cfg['business']['name']}' を初期化しました")
    print(f"  CEO: {cfg['business']['ceo_name']}, オーナー: {cfg['business']['owner_name']}")
    print(f"  月予算: ¥{cfg['business']['budget_jpy_monthly']:,}")
    print(f"  状態ファイル: {state_path}")


def cmd_research(args, cfg, workspace=None):
    sim = cfg["operations"].get("simulation_mode", True)
    emp = _make_employee(cfg, "researcher", sim)
    state_path = Path(cfg["operations"]["state_file"])
    state = load_state(state_path)
    avoid = [s["internal_code"] for s in state.get("skus", [])]
    n = cfg["employees"]["researcher"]["products_per_run"]
    result = emp.run(
        n_products=n, avoid_codes=avoid,
        out_dir=cfg["operations"]["candidates_dir"],
        workspace=workspace,
    )
    _print_result("リサーチ実施", result)
    return result


def cmd_merchandise(args, cfg, workspace=None):
    sim = cfg["operations"].get("simulation_mode", True)
    cand_dir = Path(cfg["operations"]["candidates_dir"])
    candidates_files = sorted(cand_dir.glob("*.json"))
    if not candidates_files:
        print(f"先に research を実行してください ({cand_dir} に候補がありません)")
        sys.exit(1)
    candidates = json.loads(candidates_files[-1].read_text(encoding="utf-8"))
    emp = _make_employee(cfg, "merchandiser", sim)
    result = emp.run(
        candidates=candidates, out_dir=cfg["operations"]["csv_out_dir"],
        workspace=workspace,
    )

    # SKUリストを状態に登録
    state_path = Path(cfg["operations"]["state_file"])
    state = load_state(state_path)
    new_skus = []
    for p in result.output.get("products", []):
        new_skus.append({
            "internal_code": p["internal_code"],
            "sku_jp": p["jp"]["sku"],
            "sku_en": p["en"]["sku"],
            "price_jp": p["jp"]["price"],
            "price_en": p["en"]["price"],
            "category": p["jp"].get("product_type", ""),
            "added_at": datetime.now().isoformat(timespec="seconds"),
        })
    existing = {s["internal_code"] for s in state.get("skus", [])}
    for s in new_skus:
        if s["internal_code"] not in existing:
            state.setdefault("skus", []).append(s)
    state["inventory_value_jpy"] = sum(
        int(p["jp"]["price"]) * 0.3 * 20
        for p in result.output.get("products", [])
    ) + state.get("inventory_value_jpy", 0)
    save_state(state_path, state)

    _print_result("商品ページ生成", result)
    return result


def cmd_price(args, cfg, workspace=None):
    sim = cfg["operations"].get("simulation_mode", True)
    state_path = Path(cfg["operations"]["state_file"])
    state = load_state(state_path)
    snapshot = []
    for s in state.get("skus", []):
        # シミュレーション: 売上はランダム生成 (本番ではShopify APIから取得)
        import hashlib
        h = int(hashlib.md5(s["sku_jp"].encode()).hexdigest(), 16)
        sold7 = h % 8  # 0〜7
        stock = max(20 - sold7 * 2, 0)
        cost = int(s["price_jp"] * 0.25)
        snapshot.append({
            "sku": s["sku_jp"],
            "price": s["price_jp"],
            "cost": cost,
            "sold_last_7days": sold7,
            "inventory": stock,
        })
    if not snapshot:
        print("価格判定対象のSKUがありません。先にmerchandiseを実行してください。")
        return
    emp = _make_employee(cfg, "pricing_strategist", sim)
    result = emp.run(
        sales_snapshot=snapshot, out_dir=cfg["operations"]["csv_out_dir"],
        workspace=workspace,
    )
    _print_result("価格戦略", result)
    return result


def cmd_report(args, cfg, workspace=None):
    sim = cfg["operations"].get("simulation_mode", True)
    state_path = Path(cfg["operations"]["state_file"])
    state = load_state(state_path)
    emp = _make_employee(cfg, "cfo", sim)
    result = emp.run(
        business_state=state, out_dir=cfg["operations"]["reports_dir"],
        workspace=workspace,
    )
    _print_result("CFO日次レポート", result)
    out = result.output
    print("\n┌──────────  オーナー宛 3行レポート  ──────────")
    print(f"│ {out.get('headline', '')}")
    print(f"│ {out.get('highlight_or_warning', '')}")
    print(f"│ {out.get('next_action', '')}")
    print("└────────────────────────────────────────────────")
    return result


def cmd_run_day(args, cfg):
    sim = cfg["operations"].get("simulation_mode", True)
    workspace = _make_workspace(cfg)
    workspace.reset_today()  # 新しいサイクル開始

    # CEOモデル設定 (configに無ければSonnet 4.6既定)
    cfg["employees"].setdefault("ceo", {"model": "claude-sonnet-4-6"})

    print("\n╔══════════════════════════════════════════════╗")
    print(f"║  {cfg['business']['name']} - コワーキング1日サイクル  ║")
    print(f"║  CEO: {cfg['business']['ceo_name']} / 従業員4名 / 共有チャット稼働中  ║")
    print("╚══════════════════════════════════════════════╝")

    ceo = _make_employee(cfg, "ceo", sim)

    # ── 朝会 ──
    print("\n── 朝会 (CEO Jobs) ──")
    ceo.open_day(workspace)

    # ── 業務 (リサーチ → 商品化 → 価格戦略) ──
    cmd_research(args, cfg, workspace=workspace)
    cmd_merchandise(args, cfg, workspace=workspace)
    cmd_price(args, cfg, workspace=workspace)

    # ── CFO 締め ──
    cmd_report(args, cfg, workspace=workspace)

    # ── CEO 終礼 ──
    print("\n── 終礼 (CEO Jobs 総評) ──")
    closing = ceo.close_day(workspace)
    eval_lines = closing.output.get("evaluation_3_lines", [])
    if eval_lines:
        print("\n┌──── CEO 3行総評 ────")
        for line in eval_lines:
            print(f"│ {line}")
        print("└─────────────────────")

    # ── 本日のチャットを表示 ──
    print("\n══════ 本日の社内チャット (Slack風) ══════")
    _print_chat(workspace.today_chat())
    print("\n✓ コワーキングサイクル完了。`python ai_business.py chat` でいつでも見返せます。")


def cmd_chat(args, cfg):
    """本日(または直近)の社内チャットを表示。"""
    workspace = _make_workspace(cfg)
    if args.all:
        msgs = workspace.recent_chat(n=200)
        title = "直近200発言"
    else:
        msgs = workspace.today_chat()
        title = f"本日 ({datetime.now():%Y-%m-%d})"
    print(f"\n══════ {cfg['business']['name']} 社内チャット - {title} ══════")
    _print_chat(msgs)


def cmd_status(args, cfg):
    state_path = Path(cfg["operations"]["state_file"])
    if not state_path.exists():
        print("未初期化です。`python ai_business.py init` を実行してください。")
        return
    state = load_state(state_path)
    print(f"\n■ ビジネス: {cfg['business']['name']}")
    print(f"  初期化日時: {state.get('initialized_at')}")
    print(f"  キャッシュ: ¥{state.get('cash_jpy', 0):,}")
    print(f"  月予算残: ¥{state.get('ad_budget_remaining_jpy', 0):,}")
    print(f"  在庫評価額: ¥{int(state.get('inventory_value_jpy', 0)):,}")
    print(f"  登録SKU数: {len(state.get('skus', []))}")
    print(f"  シミュレーションモード: {cfg['operations'].get('simulation_mode')}")
    skus = state.get("skus", [])
    if skus:
        print("\n  ── 登録SKU ──")
        for s in skus[-10:]:
            print(f"    {s['internal_code']} | JP:{s['sku_jp']} ¥{s['price_jp']:,} | EN:{s['sku_en']} ${s['price_en']}")


# ====================================================================== #
# エントリポイント
# ====================================================================== #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ai_business",
        description="AI自律型ECビジネス (CEO Jobs指揮)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="ビジネス状態を初期化する")
    p_init.add_argument("--force", action="store_true", help="既存状態を上書きする")
    p_init.set_defaults(func=cmd_init)

    sub.add_parser("research", help="商品候補をリサーチする").set_defaults(func=cmd_research)
    sub.add_parser("merchandise", help="商品ページCSVを生成する").set_defaults(func=cmd_merchandise)
    sub.add_parser("price", help="価格戦略を実行する").set_defaults(func=cmd_price)
    sub.add_parser("report", help="日次レポートを生成する").set_defaults(func=cmd_report)
    sub.add_parser("run-day", help="朝会→業務→終礼までのコワーキング1日サイクル").set_defaults(func=cmd_run_day)
    sub.add_parser("status", help="ビジネス状態を表示").set_defaults(func=cmd_status)

    p_chat = sub.add_parser("chat", help="社内チャットをSlack風に表示")
    p_chat.add_argument("--all", action="store_true", help="本日に限らず直近200発言を表示")
    p_chat.set_defaults(func=cmd_chat)

    return p


def main() -> None:
    args = build_parser().parse_args()
    cfg = load_config()
    args.func(args, cfg)


if __name__ == "__main__":
    main()
