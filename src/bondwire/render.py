"""Builds the digest: subject line plus plain-text and HTML bodies."""

from datetime import datetime, timezone

from . import config
from .models import FetchResult, YieldPoint

_UP = "▲"  # ▲
_DOWN = "▼"  # ▼
_FLAT = "–"  # –


def _index(points: list[YieldPoint]) -> dict[tuple[str, str], YieldPoint]:
    return {p.key: p for p in points}


def _fmt_yield(value: float) -> str:
    return f"{value:.3f}%"


def _fmt_bp(bp: float | None) -> str:
    if bp is None:
        return "n/a"
    return f"{'+' if bp > 0 else ''}{bp:.1f} bp"


def _arrow(bp: float | None) -> str:
    if bp is None or abs(bp) < 0.05:
        return _FLAT
    return _UP if bp > 0 else _DOWN


def _colour(bp: float | None) -> str:
    if bp is None or abs(bp) < 0.05:
        return "#666"
    return "#c0392b" if bp > 0 else "#1e8449"  # red = yield up, green = yield down


def _curve_bp(idx, country: str) -> tuple[float | None, float | None]:
    """(2s10s level in bp, its change in bp vs prior close)."""
    two, ten = idx.get((country, "2Y")), idx.get((country, "10Y"))
    if not two or not ten:
        return None, None
    level = round((ten.yield_pct - two.yield_pct) * 100, 1)
    change = (
        round(ten.change_bp - two.change_bp, 1)
        if ten.change_bp is not None and two.change_bp is not None
        else None
    )
    return level, change


def _spread_bp(idx, a: str, b: str, tenor: str) -> tuple[float | None, float | None]:
    pa, pb = idx.get((a, tenor)), idx.get((b, tenor))
    if not pa or not pb:
        return None, None
    level = round((pa.yield_pct - pb.yield_pct) * 100, 1)
    change = (
        round(pa.change_bp - pb.change_bp, 1)
        if pa.change_bp is not None and pb.change_bp is not None
        else None
    )
    return level, change


def _biggest_10y_mover(idx) -> YieldPoint | None:
    movers = [
        p
        for (c, t), p in idx.items()
        if t == "10Y" and c != config.EURO_AREA_CODE and p.change_bp is not None
    ]
    return max(movers, key=lambda p: abs(p.change_bp), default=None)


def _since_last(points: list[YieldPoint], prev: dict) -> tuple[str | None, list[str]]:
    prev_yields = prev.get("yields") or {}
    sent_at = prev.get("sent_at_utc")
    if not prev_yields or not sent_at:
        return None, []
    try:
        elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(sent_at)
        hours = elapsed.total_seconds() / 3600
        elapsed_str = f"{hours:.1f}h ago" if hours < 48 else f"{hours / 24:.1f}d ago"
    except ValueError:
        elapsed_str = sent_at

    moves: list[tuple[float, str]] = []
    for p in points:
        before = prev_yields.get(f"{p.country}|{p.tenor}")
        if before is None:
            continue
        delta = round((p.yield_pct - before) * 100, 1)
        if abs(delta) < 0.05:
            continue
        name = config.COUNTRY_NAMES.get(p.country, p.country)
        moves.append((abs(delta), f"{name} {p.tenor}: {before:.3f} → {p.yield_pct:.3f}% ({_fmt_bp(delta)})"))
    moves.sort(reverse=True)
    return elapsed_str, [m for _, m in moves[:6]]


# --------------------------------------------------------------------------- text
def _build_text(
    points: list[YieldPoint],
    official_only: list[YieldPoint],
    results: dict[str, FetchResult],
    prev: dict,
    ts: str,
) -> str:
    idx = _index(points)
    lines = [f"GLOBAL GOVERNMENT BOND YIELDS  —  {ts} UTC", ""]
    lines.append(f"{'':<16}{'2Y':>18}{'5Y':>18}{'10Y':>18}{'30Y':>18}{'2s10s':>14}")
    lines.append("-" * 102)

    rows = [(c, config.COUNTRY_NAMES[c]) for c, _, _ in config.COUNTRIES]
    if any(k[0] == config.EURO_AREA_CODE for k in idx):
        rows.append((config.EURO_AREA_CODE, config.EURO_AREA_NAME))

    for code, name in rows:
        cells = []
        for tenor in config.TENORS:
            p = idx.get((code, tenor))
            if p is None:
                cells.append(f"{'--':>18}")
            else:
                cells.append(f"{_fmt_yield(p.yield_pct) + ' ' + _arrow(p.change_bp):>11}{_fmt_bp(p.change_bp):>7}")
        level, change = _curve_bp(idx, code)
        curve = f"{level:+.0f}" if level is not None else "--"
        lines.append(f"{name:<16}{''.join(cells)}{curve:>14}")

    lines += ["", "KEY SPREADS (bp, vs prior close)"]
    for label, a, b, tenor in config.SPREADS:
        level, change = _spread_bp(idx, a, b, tenor)
        if level is None:
            continue
        lines.append(f"  {label:<26} {level:>8.1f}   ({_fmt_bp(change)})")

    mover = _biggest_10y_mover(idx)
    inverted = [
        config.COUNTRY_NAMES.get(c, c)
        for c in config.CURVE_COUNTRIES
        if (_curve_bp(idx, c)[0] or 0) < 0
    ]
    lines += ["", "CONTEXT"]
    if mover:
        lines.append(
            f"  Biggest 10Y move: {config.COUNTRY_NAMES.get(mover.country, mover.country)} "
            f"{_fmt_bp(mover.change_bp)} to {_fmt_yield(mover.yield_pct)}"
        )
    lines.append(f"  Inverted 2s10s: {', '.join(inverted) if inverted else 'none'}")

    elapsed_str, moves = _since_last(points, prev)
    if elapsed_str:
        lines += ["", f"SINCE LAST EMAIL ({elapsed_str})"]
        lines += [f"  {m}" for m in moves] or ["  no moves >= 0.1 bp"]

    lines += ["", "SOURCES"]
    for name, res in results.items():
        status = f"OK ({len(res.points)} pts)" if res.ok else f"FAILED: {res.error}"
        lines.append(f"  {name:<12} {status}")
    if official_only:
        lines += ["", "LAST OFFICIAL CLOSE (reference)"]
        for p in official_only:
            lines.append(
                f"  {config.COUNTRY_NAMES.get(p.country, p.country):<16} {p.tenor:<4} "
                f"{_fmt_yield(p.yield_pct)}  ({_fmt_bp(p.change_bp)})  {p.source} {p.as_of}"
            )

    lines += [
        "",
        "Yields via CNBC (near-real-time) with US Treasury / Bank of Canada / Japan MOF /",
        "Bundesbank / ECB as official backups. Colour & arrow = yield direction vs prior close.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- html
def _cell_html(p: YieldPoint | None) -> str:
    if p is None:
        return "<td style='text-align:center;color:#999'>--</td>"
    return (
        "<td style='text-align:right;white-space:nowrap'>"
        f"<b>{_fmt_yield(p.yield_pct)}</b><br>"
        f"<span style='color:{_colour(p.change_bp)};font-size:12px'>"
        f"{_arrow(p.change_bp)} {_fmt_bp(p.change_bp)}</span></td>"
    )


def _build_html(
    points: list[YieldPoint],
    official_only: list[YieldPoint],
    results: dict[str, FetchResult],
    prev: dict,
    ts: str,
) -> str:
    idx = _index(points)
    h = [
        "<html><body style='font-family:-apple-system,Segoe UI,Arial,sans-serif;color:#1a1a1a'>",
        f"<h2 style='margin-bottom:2px'>Global government bond yields</h2>",
        f"<div style='color:#666;font-size:13px'>{ts} UTC</div>",
        "<table cellpadding='8' cellspacing='0' border='0' "
        "style='border-collapse:collapse;margin-top:12px;font-size:14px'>",
        "<tr style='background:#f0f0f0'><th style='text-align:left'>Country</th>"
        "<th>2Y</th><th>5Y</th><th>10Y</th><th>30Y</th><th>2s10s</th></tr>",
    ]
    rows = [(c, config.COUNTRY_NAMES[c]) for c, _, _ in config.COUNTRIES]
    if any(k[0] == config.EURO_AREA_CODE for k in idx):
        rows.append((config.EURO_AREA_CODE, config.EURO_AREA_NAME))

    for i, (code, name) in enumerate(rows):
        bg = "#ffffff" if i % 2 == 0 else "#fafafa"
        level, change = _curve_bp(idx, code)
        curve_html = (
            f"{level:+.0f} bp<br><span style='color:{_colour(change)};font-size:12px'>"
            f"{_fmt_bp(change)}</span>"
            if level is not None
            else "<span style='color:#999'>--</span>"
        )
        h.append(
            f"<tr style='background:{bg}'><td style='text-align:left'>{name}</td>"
            + _cell_html(idx.get((code, "2Y")))
            + _cell_html(idx.get((code, "5Y")))
            + _cell_html(idx.get((code, "10Y")))
            + _cell_html(idx.get((code, "30Y")))
            + f"<td style='text-align:right;white-space:nowrap'>{curve_html}</td></tr>"
        )
    h.append("</table>")

    h.append("<h3 style='margin:18px 0 4px'>Key spreads <span style='font-weight:normal;color:#666;font-size:13px'>(bp, Δ vs prior close)</span></h3><ul style='margin-top:4px'>")
    for label, a, b, tenor in config.SPREADS:
        level, change = _spread_bp(idx, a, b, tenor)
        if level is None:
            continue
        h.append(
            f"<li>{label}: <b>{level:.1f} bp</b> "
            f"<span style='color:{_colour(change)};font-size:12px'>({_fmt_bp(change)})</span></li>"
        )
    h.append("</ul>")

    mover = _biggest_10y_mover(idx)
    inverted = [
        config.COUNTRY_NAMES.get(c, c)
        for c in config.CURVE_COUNTRIES
        if (_curve_bp(idx, c)[0] or 0) < 0
    ]
    h.append("<h3 style='margin:18px 0 4px'>Context</h3><ul style='margin-top:4px'>")
    if mover:
        h.append(
            f"<li>Biggest 10Y move: <b>{config.COUNTRY_NAMES.get(mover.country, mover.country)}</b> "
            f"{_fmt_bp(mover.change_bp)} to {_fmt_yield(mover.yield_pct)}</li>"
        )
    h.append(f"<li>Inverted 2s10s: {', '.join(inverted) if inverted else 'none'}</li></ul>")

    elapsed_str, moves = _since_last(points, prev)
    if elapsed_str:
        h.append(f"<h3 style='margin:18px 0 4px'>Since last email <span style='font-weight:normal;color:#666;font-size:13px'>({elapsed_str})</span></h3>")
        if moves:
            h.append("<ul style='margin-top:4px'>" + "".join(f"<li>{m}</li>" for m in moves) + "</ul>")
        else:
            h.append("<div style='color:#666'>no moves &ge; 0.1 bp</div>")

    failed = [f"{n} ({r.error})" for n, r in results.items() if not r.ok]
    if failed:
        h.append(
            "<p style='color:#b00;font-size:13px'><b>Source failures this run:</b> "
            + ", ".join(failed)
            + "</p>"
        )
    ok = ", ".join(f"{n}&nbsp;{len(r.points)}" for n, r in results.items() if r.ok)
    h.append(f"<p style='color:#888;font-size:12px'>Sources OK: {ok or 'none'}</p>")

    if official_only:
        h.append("<p style='color:#888;font-size:12px'><b>Last official close (reference):</b><br>")
        h.append("<br>".join(
            f"{config.COUNTRY_NAMES.get(p.country, p.country)} {p.tenor} "
            f"{_fmt_yield(p.yield_pct)} ({_fmt_bp(p.change_bp)}) — {p.source} {p.as_of}"
            for p in official_only
        ))
        h.append("</p>")

    h.append(
        "<p style='color:#aaa;font-size:11px;margin-top:16px'>Near-real-time yields via CNBC; "
        "US Treasury / Bank of Canada / Japan MOF / Bundesbank / ECB as official backups. "
        "Colour &amp; arrow show yield direction vs prior close (red = up, green = down).</p>"
    )
    h.append("</body></html>")
    return "".join(h)


def build(
    points: list[YieldPoint],
    official_only: list[YieldPoint],
    results: dict[str, FetchResult],
    prev: dict,
) -> tuple[str, str, str]:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    idx = _index(points)

    bits = []
    for code in ("US", "DE", "JP"):
        p = idx.get((code, "10Y"))
        if p:
            bits.append(f"{code}10Y {p.yield_pct:.2f}% {_arrow(p.change_bp)}{_fmt_bp(p.change_bp)}")
    subject = f"Bond yields {ts}Z — " + " | ".join(bits) if bits else f"Bond yields {ts}Z"

    text = _build_text(points, official_only, results, prev, ts)
    html = _build_html(points, official_only, results, prev, ts)
    return subject, text, html
