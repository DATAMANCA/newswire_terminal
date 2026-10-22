from dataclasses import dataclass, field
from datetime import date

BULLISH = "bullish"
BEARISH = "bearish"
NEUTRAL = "neutral"


@dataclass
class Candles:
    ticker: str
    dates: list[date]
    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[float]

    def __len__(self) -> int:
        return len(self.closes)


@dataclass
class Signal:
    ticker: str
    group: str  # "Trend", "Momentum", "Breakout", "Volume", "Divergence"
    direction: str  # BULLISH / BEARISH / NEUTRAL
    text: str


@dataclass
class Snapshot:
    """One row of the all-stocks table."""

    ticker: str
    as_of: date
    close: float
    change_pct: float | None
    rsi: float | None
    macd_above_signal: bool | None
    vs_sma_fast_pct: float | None
    vs_sma_slow_pct: float | None
    bollinger_pct_b: float | None  # 0 = lower band, 1 = upper band
    stoch_k: float | None
    from_year_high_pct: float | None
    trend: str  # "Uptrend" / "Downtrend" / "Mixed"


@dataclass
class StockResult:
    ticker: str
    ok: bool
    snapshot: Snapshot | None = None
    signals: list[Signal] = field(default_factory=list)
    premarket_price: float | None = None
    error: str | None = None
