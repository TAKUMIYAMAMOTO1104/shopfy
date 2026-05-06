"""MT5 + XM接続の診断スクリプト。

ライブトレードを始める前に、これを先に実行して以下を確認:
1. MetaTrader5 パッケージがインポートできる
2. MT5 ターミナルに接続できる
3. アカウント情報が取れる (デモかどうかも判定)
4. XAUUSD のシンボル情報・最新ティックが取れる
5. 5分足データが取れる
6. シグナル生成パイプラインがエラーなく走る

注文は一切送りません。安全に何度でも実行してください。
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "[OK]" if ok else "[NG]"
    line = f"  {mark}  {name}"
    if detail:
        line += f"  — {detail}"
    print(line)
    return ok


def main() -> int:
    print("=" * 60)
    print("XM / MT5 接続診断")
    print("=" * 60)

    # 1. パッケージ
    print("\n[1] MetaTrader5 パッケージ")
    try:
        import MetaTrader5 as mt5  # type: ignore
        check("import MetaTrader5", True, f"version={mt5.__version__}")
    except ImportError as e:
        check("import MetaTrader5", False, str(e))
        print("\n  → Windows で実行してください。")
        print("  → pip install MetaTrader5")
        return 1

    # 2. 環境変数
    print("\n[2] 環境変数 (.env)")
    login = os.getenv("MT5_LOGIN", "")
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")
    path = os.getenv("MT5_PATH", "")
    check("MT5_LOGIN", bool(login), login if login else "未設定")
    check("MT5_PASSWORD", bool(password), "***" if password else "未設定")
    check("MT5_SERVER", bool(server), server if server else "未設定")
    check("MT5_PATH (任意)", True, path if path else "未指定 (デフォルト使用)")

    if not (login and password and server):
        print("\n  → .env.example をコピーして .env を作成し、XMデモのログイン情報を記入")
        return 1

    # 3. 初期化
    print("\n[3] MT5 ターミナル初期化")
    init_kwargs: dict = {
        "login": int(login),
        "password": password,
        "server": server,
    }
    if path:
        init_kwargs["path"] = path

    if not mt5.initialize(**init_kwargs):
        err = mt5.last_error()
        check("mt5.initialize()", False, f"error={err}")
        print("\n  よくある原因:")
        print("   - MT5 デスクトップアプリが起動していない")
        print("   - サーバ名が違う (XM の正式名: 例 'XMTrading-Demo 3')")
        print("   - ログイン番号 / パスワードが間違っている")
        print("   - MT5_PATH が指している実行ファイルが別ブローカーのMT5")
        return 1
    check("mt5.initialize()", True)

    try:
        # 4. アカウント情報
        print("\n[4] アカウント情報")
        info = mt5.account_info()
        if info is None:
            check("account_info()", False, "None が返却された")
            return 1
        check("account_info()", True)
        is_demo = info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
        print(f"     login        : {info.login}")
        print(f"     server       : {info.server}")
        print(f"     name         : {info.name}")
        print(f"     currency     : {info.currency}")
        print(f"     balance      : {info.balance:.2f}")
        print(f"     equity       : {info.equity:.2f}")
        print(f"     leverage     : 1:{info.leverage}")
        print(f"     trade_mode   : {'DEMO' if is_demo else 'LIVE/REAL'}")
        check("デモ口座であること", is_demo,
              "デモです" if is_demo else "!!! 本番口座です。事故防止のためデモに切り替えてください")

        # 5. シンボル
        print("\n[5] XAUUSD シンボル")
        sym = mt5.symbol_info("XAUUSD")
        if sym is None:
            # XMだと "XAUUSD" 以外の名前のことがある (XAUUSD.,GOLDなど)
            all_syms = mt5.symbols_get()
            gold_like = [s.name for s in all_syms if "XAU" in s.name.upper() or "GOLD" in s.name.upper()][:10]
            check("symbol_info('XAUUSD')", False, f"見つからず。GOLD系候補: {gold_like}")
            print("\n  → config.py の symbol を上記の正しい名前に変更してください")
            return 1
        check("symbol_info('XAUUSD')", True)
        if not sym.visible:
            mt5.symbol_select("XAUUSD", True)
            sym = mt5.symbol_info("XAUUSD")
        print(f"     digits       : {sym.digits}")
        print(f"     point        : {sym.point}")
        print(f"     spread       : {sym.spread} points")
        print(f"     volume_min   : {sym.volume_min}")
        print(f"     volume_step  : {sym.volume_step}")
        print(f"     contract_size: {sym.trade_contract_size}")

        tick = mt5.symbol_info_tick("XAUUSD")
        if tick is None or tick.bid == 0:
            check("最新ティック取得", False, "市場クローズ中の可能性")
        else:
            spread_usd = tick.ask - tick.bid
            check("最新ティック取得", True,
                  f"bid={tick.bid:.2f} ask={tick.ask:.2f} spread={spread_usd:.2f} USD")

        # 6. 5分足ヒストリ
        print("\n[6] 5分足データ取得")
        rates = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_M5, 0, 300)
        if rates is None or len(rates) == 0:
            check("copy_rates (M5, 300本)", False, "データなし")
            return 1
        check("copy_rates (M5, 300本)", True, f"{len(rates)}本取得")

        # 7. シグナル計算パイプライン
        print("\n[7] シグナル生成パイプライン")
        try:
            import pandas as pd
            from strategy import compute_features, generate_signal
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df = df.set_index("time").rename(columns={"tick_volume": "volume"})
            df = df[["open", "high", "low", "close", "volume"]]
            feat = compute_features(df)
            sig = generate_signal(feat, len(feat) - 1)
            check("compute_features + generate_signal", True,
                  f"latest={feat.index[-1]}  side={sig.side.value}")
            last = feat.iloc[-1]
            print(f"     close={last['close']:.2f}  ema9={last['ema_fast']:.2f}  "
                  f"ema21={last['ema_slow']:.2f}  ema50={last['ema_trend']:.2f}")
            print(f"     rsi={last['rsi']:.1f}  adx={last['adx']:.1f}  atr={last['atr']:.2f}")
        except Exception as e:
            check("シグナル生成", False, f"{type(e).__name__}: {e}")
            return 1

        # 8. 取引許可
        print("\n[8] アルゴ取引設定")
        check("AutoTrading 有効", info.trade_allowed,
              "MT5の[ツール]→[オプション]→[エキスパートアドバイザ]で許可済み" if info.trade_allowed
              else "MT5アプリ上部の『アルゴリズム取引』ボタンが緑になっているか確認")

        print("\n" + "=" * 60)
        print("診断完了。問題なければ次を実行:")
        print("   python live_trader.py --dry-run    # 注文なしで観察")
        print("   python live_trader.py              # 実注文 (デモ口座)")
        print("=" * 60)
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())
