"""Data loading. Two sources:
1. Synthetic XAUUSD 5m OHLCV (for testing without MT5).
2. Real MT5 history (Windows + MetaTrader5 terminal required).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from config import CONFIG


def generate_synthetic_xauusd(
    days: int = 60,
    start_price: float = 2000.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic 5-min XAUUSD OHLCV with trending regimes + noise.

    Realistic characteristics:
    - Daily volatility ~1.0% (GOLD typical)
    - Trend regimes that switch every few days
    - Higher volatility during London/NY hours
    """
    rng = np.random.default_rng(seed)
    bars_per_day = 24 * 60 // CONFIG.timeframe_minutes
    n = days * bars_per_day

    # Time index (UTC, business + weekend treated as continuous for simplicity)
    end = pd.Timestamp.utcnow().floor("5min")
    idx = pd.date_range(end=end, periods=n, freq=f"{CONFIG.timeframe_minutes}min", tz="UTC")

    # Trend regime: switches every ~3 days, drift in {-0.0002, 0, +0.0002} per bar
    regime_len = bars_per_day * 3
    n_regimes = n // regime_len + 1
    regime_drifts = rng.choice([-0.00015, 0.0, 0.00015], size=n_regimes)
    drifts = np.repeat(regime_drifts, regime_len)[:n]

    # Volatility: higher during 7-16 UTC (London/NY)
    hours = idx.hour.to_numpy()
    base_vol = 0.0008
    vol = np.where((hours >= 7) & (hours < 17), base_vol * 1.6, base_vol * 0.7)

    # Log returns
    eps = rng.standard_normal(n)
    log_ret = drifts + vol * eps
    close = start_price * np.exp(np.cumsum(log_ret))

    # Build OHLC from close: simple model — open = previous close, high/low = close ± vol*price*|N|
    open_ = np.empty(n)
    open_[0] = start_price
    open_[1:] = close[:-1]

    intrabar_range = vol * close * (0.8 + np.abs(rng.standard_normal(n)) * 0.6)
    upper = rng.uniform(0.2, 0.8, size=n)
    high = np.maximum(open_, close) + intrabar_range * upper
    low = np.minimum(open_, close) - intrabar_range * (1.0 - upper)

    volume = rng.integers(50, 500, size=n)

    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )
    df.index.name = "time"
    return df


def load_mt5_history(symbol: str, timeframe_minutes: int, bars: int = 20_000) -> pd.DataFrame:
    """Pull real OHLCV from a running MT5 terminal. Windows-only.

    Requires: pip install MetaTrader5, MT5 desktop installed and logged into XM demo.
    """
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "MetaTrader5 package not available. Install on Windows: pip install MetaTrader5"
        ) from e

    tf_map = {1: mt5.TIMEFRAME_M1, 5: mt5.TIMEFRAME_M5, 15: mt5.TIMEFRAME_M15, 60: mt5.TIMEFRAME_H1}
    if timeframe_minutes not in tf_map:
        raise ValueError(f"Unsupported timeframe: {timeframe_minutes}")

    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    try:
        rates = mt5.copy_rates_from_pos(symbol, tf_map[timeframe_minutes], 0, bars)
    finally:
        mt5.shutdown()

    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No data for {symbol}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time")
    df = df.rename(columns={"tick_volume": "volume"})
    return df[["open", "high", "low", "close", "volume"]]
