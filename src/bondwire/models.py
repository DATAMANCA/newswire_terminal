from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class YieldPoint:
    """One government-bond yield observation."""

    country: str  # "US", "DE", "EA", ...
    tenor: str  # "2Y", "10Y", "30Y"
    yield_pct: float  # e.g. 4.758  (percent, not a fraction)
    change_bp: Optional[float]  # move vs the market's prior close, basis points
    as_of: str  # human string: "10:27 AM EDT" or "2026-08-31"
    source: str  # "CNBC", "Treasury", "BoC", "MOF", "Bundesbank", "ECB"

    @property
    def key(self) -> tuple[str, str]:
        return (self.country, self.tenor)


@dataclass
class FetchResult:
    source: str
    ok: bool
    points: list[YieldPoint]
    error: Optional[str] = None
