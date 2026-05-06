"""Signal generation. Strategy = EMA9/21 crossover, EMA50 trend filter,
RSI filter, ADX strength filter. SL/TP sized by ATR."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import pandas as pd

from config import CONFIG
from indicators import ema, rsi, atr, adx


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


@dataclass
class Signal:
    side: Side
    entry: float
    stop_loss: float
    take_profit: float
    atr_value: float


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add indicator columns to OHLCV df. df must have columns: open, high, low, close."""
    out = df.copy()
    out["ema_fast"] = ema(out["close"], CONFIG.ema_fast)
    out["ema_slow"] = ema(out["close"], CONFIG.ema_slow)
    out["ema_trend"] = ema(out["close"], CONFIG.ema_trend)
    out["rsi"] = rsi(out["close"], CONFIG.rsi_period)
    out["atr"] = atr(out["high"], out["low"], out["close"], CONFIG.atr_period)
    out["adx"] = adx(out["high"], out["low"], out["close"], CONFIG.adx_period)
    return out


def _in_trade_hours(ts: pd.Timestamp) -> bool:
    return ts.hour in CONFIG.trade_hours_utc


def generate_signal(df: pd.DataFrame, i: int) -> Signal:
    """Generate signal for bar i. Uses bar i's close (assume entry on next bar open)."""
    if i < max(CONFIG.ema_trend, CONFIG.adx_period) + 2:
        return Signal(Side.FLAT, 0, 0, 0, 0)

    row = df.iloc[i]
    prev = df.iloc[i - 1]

    # Skip if any indicator not ready
    if pd.isna(row["atr"]) or pd.isna(row["adx"]) or pd.isna(row["ema_trend"]):
        return Signal(Side.FLAT, 0, 0, 0, 0)

    # Time-of-day filter
    if not _in_trade_hours(df.index[i]):
        return Signal(Side.FLAT, 0, 0, 0, 0)

    # Trend strength filter
    if row["adx"] < CONFIG.adx_threshold:
        return Signal(Side.FLAT, 0, 0, 0, 0)

    crossed_up = prev["ema_fast"] <= prev["ema_slow"] and row["ema_fast"] > row["ema_slow"]
    crossed_dn = prev["ema_fast"] >= prev["ema_slow"] and row["ema_fast"] < row["ema_slow"]

    price = row["close"]
    a = row["atr"]

    if crossed_up and price > row["ema_trend"] and row["rsi"] < CONFIG.rsi_long_max:
        return Signal(
            Side.LONG,
            entry=price,
            stop_loss=price - CONFIG.sl_atr_mult * a,
            take_profit=price + CONFIG.tp_atr_mult * a,
            atr_value=a,
        )
    if crossed_dn and price < row["ema_trend"] and row["rsi"] > CONFIG.rsi_short_min:
        return Signal(
            Side.SHORT,
            entry=price,
            stop_loss=price + CONFIG.sl_atr_mult * a,
            take_profit=price - CONFIG.tp_atr_mult * a,
            atr_value=a,
        )
    return Signal(Side.FLAT, 0, 0, 0, 0)


def position_size(balance: float, entry: float, stop_loss: float) -> float:
    """Lot size that risks `risk_per_trade` of balance. XAUUSD: 1 lot = 100 oz, 1$ move = $100."""
    risk_usd = balance * CONFIG.risk_per_trade
    sl_distance = abs(entry - stop_loss)
    if sl_distance <= 0:
        return 0.0
    raw_lot = risk_usd / (sl_distance * CONFIG.contract_size)
    # round down to lot_step
    lots = max(CONFIG.min_lot, (raw_lot // CONFIG.lot_step) * CONFIG.lot_step)
    return round(lots, 2)
