"""Bar-by-bar backtest engine.

Rules:
- Signal computed on bar i close → trade entered at bar i+1 open (no look-ahead).
- One position at a time.
- SL/TP checked on each bar's high/low. If both hit on same bar, assume SL hit (conservative).
- Spread modeled by widening entry/exit by spread_usd / 2 each side.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import numpy as np
import pandas as pd

from config import CONFIG
from strategy import compute_features, generate_signal, position_size, Side
from data_loader import generate_synthetic_xauusd


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: str
    entry: float
    exit: float
    stop_loss: float
    take_profit: float
    lots: float
    pnl_usd: float
    reason: str  # "TP" | "SL" | "EOD"


def run_backtest(df: pd.DataFrame, verbose: bool = False) -> tuple[list[Trade], pd.Series]:
    df = compute_features(df)
    balance = CONFIG.initial_balance
    equity_curve = [balance]
    equity_index = [df.index[0]]
    trades: list[Trade] = []

    open_trade: Trade | None = None
    half_spread = CONFIG.spread_usd / 2.0

    for i in range(len(df) - 1):
        bar_next = df.iloc[i + 1]

        # Manage open trade on bar i+1
        if open_trade is not None:
            high, low = bar_next["high"], bar_next["low"]
            hit_sl = (open_trade.side == Side.LONG.value and low <= open_trade.stop_loss) or (
                open_trade.side == Side.SHORT.value and high >= open_trade.stop_loss
            )
            hit_tp = (open_trade.side == Side.LONG.value and high >= open_trade.take_profit) or (
                open_trade.side == Side.SHORT.value and low <= open_trade.take_profit
            )
            exit_price = None
            reason = ""
            if hit_sl and hit_tp:
                exit_price, reason = open_trade.stop_loss, "SL"  # conservative
            elif hit_sl:
                exit_price, reason = open_trade.stop_loss, "SL"
            elif hit_tp:
                exit_price, reason = open_trade.take_profit, "TP"

            if exit_price is not None:
                # Apply exit-side spread cost
                if open_trade.side == Side.LONG.value:
                    fill = exit_price - half_spread
                    pnl = (fill - open_trade.entry) * open_trade.lots * CONFIG.contract_size
                else:
                    fill = exit_price + half_spread
                    pnl = (open_trade.entry - fill) * open_trade.lots * CONFIG.contract_size
                pnl -= CONFIG.commission_per_lot * open_trade.lots
                open_trade.exit = fill
                open_trade.exit_time = df.index[i + 1]
                open_trade.pnl_usd = pnl
                open_trade.reason = reason
                balance += pnl
                trades.append(open_trade)
                if verbose:
                    print(f"{open_trade.exit_time}  {open_trade.side}  {reason}  PnL={pnl:+.2f}  bal={balance:.2f}")
                open_trade = None

        # Generate new signal on bar i (no open trade, enter on i+1 open)
        if open_trade is None:
            sig = generate_signal(df, i)
            if sig.side != Side.FLAT:
                # Entry on next bar open + spread
                raw_open = bar_next["open"]
                if sig.side == Side.LONG:
                    entry_fill = raw_open + half_spread
                else:
                    entry_fill = raw_open - half_spread
                lots = position_size(balance, entry_fill, sig.stop_loss)
                if lots > 0:
                    open_trade = Trade(
                        entry_time=df.index[i + 1],
                        exit_time=df.index[i + 1],
                        side=sig.side.value,
                        entry=entry_fill,
                        exit=0.0,
                        stop_loss=sig.stop_loss,
                        take_profit=sig.take_profit,
                        lots=lots,
                        pnl_usd=0.0,
                        reason="",
                    )

        equity_curve.append(balance + _floating_pnl(open_trade, bar_next))
        equity_index.append(df.index[i + 1])

    equity = pd.Series(equity_curve, index=equity_index, name="equity")
    return trades, equity


def _floating_pnl(trade: Trade | None, bar: pd.Series) -> float:
    if trade is None:
        return 0.0
    if trade.side == Side.LONG.value:
        return (bar["close"] - trade.entry) * trade.lots * CONFIG.contract_size
    return (trade.entry - bar["close"]) * trade.lots * CONFIG.contract_size


def metrics(trades: list[Trade], equity: pd.Series) -> dict:
    if not trades:
        return {"trades": 0, "note": "no trades"}
    pnls = np.array([t.pnl_usd for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    final = float(equity.iloc[-1])
    initial = CONFIG.initial_balance
    rolling_max = equity.cummax()
    dd = (equity - rolling_max) / rolling_max
    return {
        "trades": int(len(trades)),
        "win_rate": float(len(wins) / len(trades)),
        "avg_win_usd": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_usd": float(losses.mean()) if len(losses) else 0.0,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float("inf"),
        "expectancy_usd": float(pnls.mean()),
        "total_pnl_usd": float(pnls.sum()),
        "return_pct": float((final - initial) / initial * 100.0),
        "max_drawdown_pct": float(dd.min() * 100.0),
        "final_balance_usd": final,
    }


def save_results(trades: list[Trade], equity: pd.Series, m: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([asdict(t) for t in trades]).to_csv(out_dir / "trades.csv", index=False)
    equity.to_csv(out_dir / "equity.csv")
    (out_dir / "metrics.json").write_text(json.dumps(m, indent=2, default=str))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=120, help="Synthetic data length in days")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    print(f"Generating {args.days} days of synthetic XAUUSD 5m data (seed={args.seed})...")
    df = generate_synthetic_xauusd(days=args.days, seed=args.seed)
    print(f"  bars: {len(df)}, range: {df.index[0]} → {df.index[-1]}")
    print(f"  price: {df['close'].iloc[0]:.2f} → {df['close'].iloc[-1]:.2f}")

    print("\nRunning backtest...")
    trades, equity = run_backtest(df, verbose=args.verbose)
    m = metrics(trades, equity)

    print("\n=== Backtest Results ===")
    for k, v in m.items():
        if isinstance(v, float):
            print(f"  {k:22s} {v:>12.4f}")
        else:
            print(f"  {k:22s} {v}")

    out = Path(__file__).parent / CONFIG.results_dir
    save_results(trades, equity, m, out)
    print(f"\nResults saved to: {out}/")


if __name__ == "__main__":
    main()
