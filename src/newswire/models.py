from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

Source = Literal["EDGAR", "YAHOO"]


@dataclass
class NewsItem:
    source: Source
    ticker: str
    uid: str
    title: str
    url: str
    published_at: datetime
    extra: dict = field(default_factory=dict)


@dataclass
class SourceResult:
    source: Source
    ok: bool
    items: list[NewsItem] = field(default_factory=list)
    error: Optional[str] = None
