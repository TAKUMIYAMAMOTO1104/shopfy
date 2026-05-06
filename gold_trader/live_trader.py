"""Live demo trader for XM via MetaTrader5 (Windows-only).

Loop:
1. Pull latest closed 5m bar from MT5.
2. Compute features and signal.
3. If FLAT → consider new entry. Submit market order with SL/TP.
4. Sleep until next bar close.

Safety:
- Demo only by default (account check warns if live).
- Single position cap.
- Risk = 1% per trade.
"""
from __future__ import annotations
import os
import time
import logging
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

from config import CONFIG
from strategy import compute_features, generate_signal, position_size, Side

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("live")


def _mt5():
    try:
        import MetaTrader5 as mt5  # type: ignore
        return mt5
    except ImportError as e:
        raise RuntimeError(
            "MetaTrader5 not installed. On Windows: pip install MetaTrader5\n"
            "(this script must run on Windows with MT5 terminal installed)"
        ) from e


def init_mt5():
    mt5 = _mt5()
    login = int(os.getenv("MT5_LOGIN", "0"))
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")
    path = os.getenv("MT5_PATH") or None

    kwargs = {}
    if path:
        kwargs["path"] = path
    if login and password and server:
        kwargs.update(login=login, password=password, server=server)

    if not mt5.initialize(**kwargs):
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")

    info = mt5.account_info()
    if info is None:
        raise RuntimeError("Could not fetch account info")

    log.info("Connected: account=%s server=%s balance=%.2f currency=%s",
             info.login, info.server, info.balance, info.currency)
    if info.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        log.warning("!!! Account is NOT a demo account. Set TRADE_ENABLED=false to dry-run.")
    return mt5


def fetch_latest_bars(mt5, n: int = 300) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(CONFIG.symbol, mt5.TIMEFRAME_M5, 0, n)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No rates for {CONFIG.symbol}")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time").rename(columns={"tick_volume": "volume"})
    return df[["open", "high", "low", "close", "volume"]]


def has_open_position(mt5) -> bool:
    pos = mt5.positions_get(symbol=CONFIG.symbol)
    return pos is not None and len(pos) > 0


def submit_order(mt5, side: Side, lots: float, sl: float, tp: float) -> dict:
    tick = mt5.symbol_info_tick(CONFIG.symbol)
    if tick is None:
        raise RuntimeError(f"No tick for {CONFIG.symbol}")
    if side == Side.LONG:
        order_type, price = mt5.ORDER_TYPE_BUY, tick.ask
    else:
        order_type, price = mt5.ORDER_TYPE_SELL, tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": CONFIG.symbol,
        "volume": float(lots),
        "type": order_type,
        "price": float(price),
        "sl": float(sl),
        "tp": float(tp),
        "deviation": 20,
        "magic": 20260506,
        "comment": "ai-gold-trader",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    return {"retcode": result.retcode, "comment": result.comment, "order": result.order, "price": result.price}


def trading_loop(poll_seconds: int = 30, dry_run: bool = False):
    mt5 = init_mt5()
    last_bar_time: pd.Timestamp | None = None
    log.info("Loop started. dry_run=%s", dry_run)

    try:
        while True:
            try:
                df = fetch_latest_bars(mt5, n=300)
                # Use only fully closed bars: drop the last (in-progress) bar
                df_closed = df.iloc[:-1]
                latest_bar_time = df_closed.index[-1]

                if last_bar_time != latest_bar_time:
                    last_bar_time = latest_bar_time
                    feat = compute_features(df_closed)
                    sig = generate_signal(feat, len(feat) - 1)
                    log.info("Bar %s close=%.2f side=%s", latest_bar_time, df_closed["close"].iloc[-1], sig.side.value)

                    if sig.side != Side.FLAT and not has_open_position(mt5):
                        info = mt5.account_info()
                        lots = position_size(info.balance, sig.entry, sig.stop_loss)
                        if lots > 0:
                            log.info("ENTRY %s lots=%.2f entry=%.2f sl=%.2f tp=%.2f",
                                     sig.side.value, lots, sig.entry, sig.stop_loss, sig.take_profit)
                            if dry_run:
                                log.info("(dry_run) order skipped")
                            else:
                                res = submit_order(mt5, sig.side, lots, sig.stop_loss, sig.take_profit)
                                log.info("Order result: %s", res)
                time.sleep(poll_seconds)
            except KeyboardInterrupt:
                raise
            except Exception:
                log.exception("Loop iteration failed; continuing in 30s")
                time.sleep(30)
    finally:
        mt5.shutdown()
        log.info("MT5 shut down")


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="No orders sent; signals only")
    p.add_argument("--poll", type=int, default=30, help="Polling seconds")
    args = p.parse_args()
    trading_loop(poll_seconds=args.poll, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
