"""Trading configuration. Edit values here, no other file changes needed."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # 銘柄・時間足
    symbol: str = "XAUUSD"
    timeframe_minutes: int = 5

    # 資金・リスク
    initial_balance: float = 10_000.0      # USD
    risk_per_trade: float = 0.01           # 1% / trade
    max_concurrent_positions: int = 1
    contract_size: float = 100.0           # XAUUSD = 100 oz / lot
    min_lot: float = 0.01
    lot_step: float = 0.01
    spread_usd: float = 0.30               # GOLDの想定スプレッド (USD)
    commission_per_lot: float = 0.0

    # シグナル生成
    ema_fast: int = 9
    ema_slow: int = 21
    ema_trend: int = 50                    # トレンドフィルタ
    rsi_period: int = 14
    rsi_long_max: float = 70.0             # ロング: RSIがこれ未満
    rsi_short_min: float = 30.0            # ショート: RSIがこれ超
    atr_period: int = 14
    adx_period: int = 14
    adx_threshold: float = 20.0            # トレンドが弱い時はノートレード

    # SL/TP (ATR倍率) — リスクリワード 1:1.66
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 2.5

    # 取引時間フィルタ (UTC) — ロンドン/NYのオーバーラップを中心に
    trade_hours_utc: tuple = (7, 8, 9, 10, 11, 12, 13, 14, 15, 16)

    # バックテスト出力
    results_dir: str = "logs"


CONFIG = Config()
