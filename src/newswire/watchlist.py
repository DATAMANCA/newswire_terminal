from pathlib import Path


def load_watchlist(path: Path) -> list[str]:
    if not path.exists():
        return []

    tickers: list[str] = []
    seen: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        ticker = line.split()[0].upper()
        if ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    return tickers
