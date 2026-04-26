#!/usr/bin/env python3
"""ContentLab Tokyo - AI自律型コンテンツ工場 CLI (コワーキング版)。

オーナーが叩く窓口。CEO Jobs と AI従業員4名(トレンドリサーチ部長/脚本家/
演出ディレクター/CFO)が共有チャットで会話・引き継ぎ・指摘し合いながら
1日分の制作サイクルを自走する。

使い方:
  python ai_business.py doctor         # 環境診断 (本番化前に必ず実行)
  python ai_business.py init           # ビジネス状態を初期化
  python ai_business.py research       # トレンド部長にトピック候補を出させる
  python ai_business.py write          # 脚本家に長尺+Shortsを書かせる
  python ai_business.py direct         # ディレクターにサムネ・タイトル等を作らせる
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
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ai_employees import (
    CEO,
    CFO,
    Director,
    Scriptwriter,
    TrendResearcher,
    Workspace,
    _read_monthly_cost_jpy,
)
from utils.logger import setup_logger

load_dotenv()
logger = setup_logger("ai_business")

CONFIG_PATH = Path("config/business.yaml")


# ====================================================================== #
# 設定 & 状態
# ====================================================================== #

def load_config() -> dict[str, Any]:
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
        "monthly_budget_jpy": 100000,
        "videos": [],            # [{"internal_code", "label", "platform", "language", "title", "script_path", "package_path", "added_at"}]
        "videos_produced_today": 0,
        "videos_posted_today": 0,
        "views_24h": 0,
        "ad_revenue_jpy": 0,
        "subs_delta": 0,
        "top_videos": [],
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
        "trend_researcher": TrendResearcher,
        "scriptwriter": Scriptwriter,
        "director": Director,
        "cfo": CFO,
        "ceo": CEO,
    }
    monthly_budget = cfg.get("budget_allocation", {}).get("api_and_ops_jpy", 10_000)
    return cls_map[role_key](
        model=role["model"],
        simulation_mode=sim,
        monthly_budget_jpy=monthly_budget,
    )


def _make_workspace(cfg: dict) -> Workspace:
    root = cfg.get("operations", {}).get("cowork_dir", "data/cowork")
    return Workspace(root=root)


# Slack風表示用の色付け
HANDLE_COLORS = {
    "@ceo":          "\033[1;33m",
    "@researcher":   "\033[36m",
    "@scriptwriter": "\033[32m",
    "@director":     "\033[35m",
    "@cfo":          "\033[34m",
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
    state["monthly_budget_jpy"] = cfg["business"]["budget_jpy_monthly"]
    save_state(state_path, state)
    print(f"\n✓ ビジネス '{cfg['business']['name']}' を初期化しました")
    print(f"  CEO: {cfg['business']['ceo_name']}, オーナー: {cfg['business']['owner_name']}")
    print(f"  ジャンル: {cfg['business']['genre']}")
    print(f"  月予算: ¥{cfg['business']['budget_jpy_monthly']:,}")
    print(f"  状態ファイル: {state_path}")


def cmd_research(args, cfg, workspace=None):
    sim = cfg["operations"].get("simulation_mode", True)
    emp = _make_employee(cfg, "trend_researcher", sim)
    state_path = Path(cfg["operations"]["state_file"])
    state = load_state(state_path)
    avoid = list({v.get("internal_code") for v in state.get("videos", []) if v.get("internal_code")})
    n = cfg["employees"]["trend_researcher"].get("topics_per_run", 3)
    result = emp.run(
        n_topics=n, avoid_codes=avoid,
        out_dir=cfg["operations"]["trends_dir"],
        workspace=workspace,
    )
    _print_result("トレンドリサーチ", result)
    return result


def cmd_write(args, cfg, workspace=None):
    sim = cfg["operations"].get("simulation_mode", True)
    trends_dir = Path(cfg["operations"]["trends_dir"])
    files = sorted(trends_dir.glob("*.json"))
    if not files:
        print(f"先に research を実行してください ({trends_dir} にトレンドJSONがありません)")
        sys.exit(1)
    trends = json.loads(files[-1].read_text(encoding="utf-8"))
    # top_pick優先、なければ最初のトピック
    top_code = trends.get("top_pick_code")
    topics = trends.get("topics", [])
    topic = next((t for t in topics if t.get("internal_code") == top_code), topics[0] if topics else None)
    if not topic:
        print("トピックが空です。research をやり直してください。")
        sys.exit(1)

    emp = _make_employee(cfg, "scriptwriter", sim)
    shorts_n = cfg["employees"]["scriptwriter"].get("shorts_per_topic", 3)
    result = emp.run(
        topic=topic,
        out_dir=cfg["operations"]["scripts_dir"],
        shorts_per_topic=shorts_n,
        workspace=workspace,
    )
    _print_result("脚本執筆", result)
    return result


def cmd_direct(args, cfg, workspace=None):
    sim = cfg["operations"].get("simulation_mode", True)
    scripts_dir = Path(cfg["operations"]["scripts_dir"])
    # 最新日付ディレクトリの最新コードのscripts.jsonを拾う
    date = datetime.now().strftime("%Y-%m-%d")
    today_dir = scripts_dir / date
    if not today_dir.exists():
        print(f"先に write を実行してください ({today_dir} がありません)")
        sys.exit(1)
    code_dirs = sorted([d for d in today_dir.iterdir() if d.is_dir()])
    if not code_dirs:
        print(f"脚本がありません: {today_dir}")
        sys.exit(1)
    scripts_json = code_dirs[-1] / "scripts.json"
    scripts = json.loads(scripts_json.read_text(encoding="utf-8"))

    emp = _make_employee(cfg, "director", sim)
    result = emp.run(
        scripts=scripts,
        out_dir=cfg["operations"]["production_dir"],
        workspace=workspace,
    )

    # 状態に動画を登録
    state_path = Path(cfg["operations"]["state_file"])
    state = load_state(state_path)
    code = result.output.get("internal_code", "CTL-XXX")
    new_videos = []
    for p in result.output.get("packages", []):
        new_videos.append({
            "internal_code": code,
            "label": p.get("label"),
            "platform": p.get("platform"),
            "language": p.get("language"),
            "recommended_title": (p.get("title_variants") or [""])[p.get("recommended_title_index", 0)],
            "added_at": datetime.now().isoformat(timespec="seconds"),
            "posted": False,
        })
    existing = {(v.get("internal_code"), v.get("label")) for v in state.get("videos", [])}
    for v in new_videos:
        if (v["internal_code"], v["label"]) not in existing:
            state.setdefault("videos", []).append(v)
    state["videos_produced_today"] = len(new_videos)
    save_state(state_path, state)

    _print_result("演出パッケージ生成", result)
    return result


def cmd_report(args, cfg, workspace=None):
    sim = cfg["operations"].get("simulation_mode", True)
    state_path = Path(cfg["operations"]["state_file"])
    state = load_state(state_path)
    # APIコスト消化を含めて状態に注入
    used = _read_monthly_cost_jpy()
    budget = cfg.get("budget_allocation", {}).get("api_and_ops_jpy", 10_000)
    state["api_spend_jpy"] = int(used)
    state["monthly_budget_remaining_jpy"] = max(0, int(budget - used))
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
    workspace.reset_today()

    cfg["employees"].setdefault("ceo", {"model": "claude-sonnet-4-6"})

    print("\n╔══════════════════════════════════════════════╗")
    print(f"║  {cfg['business']['name']} - コワーキング1日サイクル  ║")
    print(f"║  CEO: {cfg['business']['ceo_name']} / 従業員4名 / 共有チャット稼働中  ║")
    print("╚══════════════════════════════════════════════╝")

    ceo = _make_employee(cfg, "ceo", sim)

    print("\n── 朝会 (CEO Jobs) ──")
    ceo.open_day(workspace)

    cmd_research(args, cfg, workspace=workspace)
    cmd_write(args, cfg, workspace=workspace)
    cmd_direct(args, cfg, workspace=workspace)
    cmd_report(args, cfg, workspace=workspace)

    print("\n── 終礼 (CEO Jobs 総評) ──")
    closing = ceo.close_day(workspace)
    eval_lines = closing.output.get("evaluation_3_lines", [])
    if eval_lines:
        print("\n┌──── CEO 3行総評 ────")
        for line in eval_lines:
            print(f"│ {line}")
        print("└─────────────────────")

    print("\n══════ 本日の社内チャット (Slack風) ══════")
    _print_chat(workspace.today_chat())
    print("\n✓ コワーキングサイクル完了。`python ai_business.py chat` でいつでも見返せます。")


def cmd_doctor(args, cfg):
    """環境を診断し、本番運用前のチェックリストを返す。"""
    print("\n══════ 環境診断 (Doctor) ══════\n")
    issues: list[str] = []
    ok: list[str] = []

    try:
        import anthropic  # noqa: F401
        ok.append("anthropic SDK: インストール済み")
    except ImportError:
        issues.append("anthropic SDK 未インストール → `pip install -r requirements.txt`")

    try:
        import yaml  # noqa: F401
        ok.append("PyYAML: インストール済み")
    except ImportError:
        issues.append("PyYAML 未インストール → `pip install -r requirements.txt`")

    if Path(".env").exists():
        ok.append(".env ファイル: 存在")
    else:
        issues.append(".env が無い → `cp .env.example .env` で雛形を作成し、APIキーを記入")

    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        issues.append("ANTHROPIC_API_KEY 未設定 → .env に記入")
    elif not key.startswith("sk-ant-"):
        issues.append("ANTHROPIC_API_KEY 形式不正 (sk-ant- で始まるはず)")
    else:
        ok.append(f"ANTHROPIC_API_KEY: 設定済み (...{key[-4:]})")

    if Path("config/business.yaml").exists():
        ok.append("config/business.yaml: 存在")
    else:
        issues.append("config/business.yaml が無い")

    used = _read_monthly_cost_jpy()
    budget = cfg.get("budget_allocation", {}).get("api_and_ops_jpy", 10_000)
    pct = round(used / budget * 100, 1) if budget else 0
    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
    print(f"  月次API予算消化:  ¥{used:,.0f} / ¥{budget:,} ({pct}%)")
    print(f"                    [{bar}]\n")
    if used >= budget:
        issues.append(f"月次予算超過 ¥{used:,.0f} ≥ ¥{budget:,} → API呼び出しがブロックされます")

    sim = cfg["operations"].get("simulation_mode", True)
    if sim:
        ok.append("simulation_mode: true (Claude API は呼ばれません)")
    else:
        ok.append("simulation_mode: false (本番モード・実APIコール)")

    api_ping_ok = False
    if key and key.startswith("sk-ant-") and not any("anthropic SDK" in i for i in issues):
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=key)
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,
                messages=[{"role": "user", "content": "respond with 'pong'"}],
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            ok.append(f"Claude API ping: 成功 (応答: {text.strip()[:30]!r})")
            api_ping_ok = True
        except Exception as e:
            issues.append(f"Claude API ping 失敗: {e}")

    print("  ── OK ──")
    for o in ok:
        print(f"  ✓ {o}")
    if issues:
        print("\n  ── 要対処 ──")
        for i in issues:
            print(f"  ✗ {i}")
        print("\n上記を解消後、再度 `python ai_business.py doctor` を実行してください。")
        sys.exit(1)
    else:
        print("\n✓ 全チェックOK。本番運用OKです。")
        if not sim and api_ping_ok:
            print("  実Claudeで動かす準備完了 → `python ai_business.py run-day`")


def cmd_chat(args, cfg):
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
    used = _read_monthly_cost_jpy()
    budget = cfg.get("budget_allocation", {}).get("api_and_ops_jpy", 10_000)
    print(f"\n■ ビジネス: {cfg['business']['name']}")
    print(f"  ジャンル: {cfg['business']['genre']}")
    print(f"  初期化日時: {state.get('initialized_at')}")
    print(f"  月予算 (合計): ¥{state.get('monthly_budget_jpy', 0):,}")
    print(f"  API消化額/予算: ¥{used:,.0f} / ¥{budget:,}")
    print(f"  本日生産動画数: {state.get('videos_produced_today', 0)}")
    print(f"  累計動画数: {len(state.get('videos', []))}")
    print(f"  シミュレーションモード: {cfg['operations'].get('simulation_mode')}")
    videos = state.get("videos", [])
    if videos:
        print("\n  ── 直近の動画ラインナップ ──")
        for v in videos[-10:]:
            print(f"    [{v.get('platform','?'):14}] {v.get('label','?'):15} ({v.get('language','?'):2}) {v.get('recommended_title','')[:40]}")


# ====================================================================== #
# エントリポイント
# ====================================================================== #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ai_business",
        description="ContentLab Tokyo - AI自律型コンテンツ工場 (CEO Jobs指揮)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="ビジネス状態を初期化する")
    p_init.add_argument("--force", action="store_true", help="既存状態を上書きする")
    p_init.set_defaults(func=cmd_init)

    sub.add_parser("research", help="トレンドトピックをリサーチする").set_defaults(func=cmd_research)
    sub.add_parser("write", help="長尺+Shorts脚本を執筆する").set_defaults(func=cmd_write)
    sub.add_parser("direct", help="演出パッケージ(タイトル/サムネ/説明文)を作る").set_defaults(func=cmd_direct)
    sub.add_parser("report", help="CFOの日次レポートを生成する").set_defaults(func=cmd_report)
    sub.add_parser("run-day", help="朝会→業務→終礼までのコワーキング1日サイクル").set_defaults(func=cmd_run_day)
    sub.add_parser("status", help="ビジネス状態を表示").set_defaults(func=cmd_status)

    p_chat = sub.add_parser("chat", help="社内チャットをSlack風に表示")
    p_chat.add_argument("--all", action="store_true", help="本日に限らず直近200発言を表示")
    p_chat.set_defaults(func=cmd_chat)

    sub.add_parser("doctor", help="環境を診断 (本番運用前のチェックリスト)").set_defaults(func=cmd_doctor)

    return p


def main() -> None:
    args = build_parser().parse_args()
    cfg = load_config()
    args.func(args, cfg)


if __name__ == "__main__":
    main()
