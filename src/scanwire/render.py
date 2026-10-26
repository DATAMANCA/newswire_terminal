"""Builds the scan email (subject, plain text, HTML), grouped by sector."""

from collections import Counter
from datetime import date
from html import escape

from . import config, scan
from .scan import Hit, Outcome

GREEN = "#1a7f37"
RED = "#c62828"
GREY = "#666666"
_HEAD = "padding:4px 8px;border-bottom:2px solid #333;text-align:right;white-space:nowrap"
_CELL = "padding:3px 8px;border-bottom:1px solid #ddd;text-align:right;white-space:nowrap"
NAME_WIDTH = 34


def money(v: float) -> str:
    if v >= 1e12:
        return f"${v / 1e12:.1f}T"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    return f"${v / 1e6:.0f}M"


def slope_label(slope: float | None) -> str:
    if slope is None:
        return "n/a"
    if abs(slope) < config.FLAT_SLOPE_PCT:
        return f"Flat {slope:+.1f}%"
    return f"{'Rising' if slope > 0 else 'Falling'} {slope:+.1f}%"


def came_from_label(came_from: str) -> str:
    return {"above": "↓ from above", "below": "↑ from below"}.get(came_from, "n/a")


def short_name(name: str) -> str:
    for tail in (" Class A Common Stock", " Common Stock", " Ordinary Shares"):
        name = name.replace(tail, "")
    return name if len(name) <= NAME_WIDTH else name[: NAME_WIDTH - 1] + "…"


def by_sector(hits: list[Hit]) -> list[tuple[str, list[Hit]]]:
    """Sectors with the most hits first; tightest to the EMA first inside each."""
    groups: dict[str, list[Hit]] = {}
    for h in hits:
        groups.setdefault(h.company.sector, []).append(h)
    for rows in groups.values():
        rows.sort(key=lambda h: abs(h.distance_pct))
    return sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))


def build(hits: list[Hit], outcomes: list[Outcome], as_of: date, first_run: bool) -> tuple[str, str, str]:
    above = sum(h.distance_pct >= 0 for h in hits)
    new = sum(h.new for h in hits)
    reasons = Counter(o.reason for o in outcomes)
    failed = [o for o in outcomes if o.reason == scan.FAILED]
    day = f"{as_of:%a} {as_of.day} {as_of:%b}"

    subject = f"200 EMA scan {day}: {len(hits)} stocks within ±{config.BAND_PCT:g}%"
    if not first_run:
        subject += f" ({new} new)"
    intro = (
        f"Close on {as_of:%A %d %B %Y}. {len(hits)} stocks within ±{config.BAND_PCT:g}% of their "
        f"{config.EMA_PERIOD}-day EMA: {above} just above, {len(hits) - above} just below"
        + ("." if first_run else f", {new} new since the last scan.")
    )
    scanned = (
        f"Scanned {len(outcomes) - len(failed):,} US companies worth {money(config.MIN_MARKET_CAP)}+. "
        f"Left out: {reasons[scan.LOW_PRICE]:,} under ${config.MIN_PRICE:g}, "
        f"{reasons[scan.LOW_VOLUME]:,} averaging under {config.MIN_AVG_VOLUME:,} shares/day, "
        f"{reasons[scan.SHORT_HISTORY]:,} with under {config.EMA_PERIOD} days of history."
    )
    groups = by_sector(hits)
    return subject, _text(intro, scanned, groups, failed, first_run), _html(intro, scanned, groups, failed, first_run)


def _text(intro, scanned, groups, failed, first_run) -> str:
    lines = [intro, scanned, ""]
    if first_run:
        lines += ["First scan: NEW tags start from the next one.", ""]
    for sector, rows in groups:
        lines.append(f"== {sector} ({len(rows)}) ==")
        for h in rows:
            lines.append(
                f"{'NEW ' if h.new else '    '}{h.company.ticker:<6} {short_name(h.company.name):<{NAME_WIDTH}} "
                f"${h.close:>9,.2f}  EMA ${h.ema:>9,.2f}  {h.distance_pct:+.2f}%  "
                f"{came_from_label(h.came_from):<13} {slope_label(h.slope_pct):<14} "
                f"{money(h.company.market_cap):>7}  {h.days_in_band}d"
            )
        lines.append("")
    if failed:
        lines.append("Could not load: " + ", ".join(o.ticker for o in failed))
    return "\n".join(lines) + "\n"


def _new_badge() -> str:
    return (
        '<span style="background:#e65100;color:#fff;font-size:11px;font-weight:bold;'
        'padding:1px 5px;border-radius:3px">NEW</span>'
    )


def _html(intro, scanned, groups, failed, first_run) -> str:
    parts = [
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#000;max-width:1000px">',
        f'<h2 style="margin:0 0 4px">{config.EMA_PERIOD} EMA scan</h2>',
        f'<p style="margin:0 0 4px">{escape(intro)}</p>',
        f'<p style="margin:0 0 10px;color:{GREY};font-size:12px">{escape(scanned)}</p>',
    ]
    if first_run:
        parts.append(f'<p style="margin:0 0 10px;color:{GREY}">First scan: NEW tags start from the next one.</p>')
    parts.append(
        '<p style="margin:0 0 14px">'
        + " &nbsp;·&nbsp; ".join(f"{escape(s)} <b>{len(rows)}</b>" for s, rows in groups)
        + "</p>"
    )

    cols = ["", "Ticker", "Name", "Price", f"{config.EMA_PERIOD} EMA", "Distance",
            "Came from", f"EMA slope ({config.SLOPE_LOOKBACK}d)", "Mkt cap", "Days in band"]
    head = "<tr>" + "".join(
        f'<th style="{_HEAD}{";text-align:left" if c in ("Ticker", "Name", "Came from") else ""}">{c}</th>'
        for c in cols
    ) + "</tr>"
    for sector, rows in groups:
        parts.append(f'<h3 style="margin:18px 0 6px">{escape(sector)} ({len(rows)})</h3>')
        parts.append('<table style="border-collapse:collapse;font-size:13px">' + head)
        for h in rows:
            dist_colour = GREEN if h.distance_pct >= 0 else RED
            slope_colour = (
                GREY if h.slope_pct is None or abs(h.slope_pct) < config.FLAT_SLOPE_PCT
                else GREEN if h.slope_pct > 0 else RED
            )
            parts.append(
                "<tr>"
                f'<td style="{_CELL}">{_new_badge() if h.new else ""}</td>'
                f'<td style="{_CELL};text-align:left"><b>{escape(h.company.ticker)}</b></td>'
                f'<td style="{_CELL};text-align:left">{escape(short_name(h.company.name))}</td>'
                f'<td style="{_CELL}">${h.close:,.2f}</td>'
                f'<td style="{_CELL}">${h.ema:,.2f}</td>'
                f'<td style="{_CELL};color:{dist_colour}"><b>{h.distance_pct:+.2f}%</b></td>'
                f'<td style="{_CELL};text-align:left">{came_from_label(h.came_from)}</td>'
                f'<td style="{_CELL};color:{slope_colour}">{slope_label(h.slope_pct)}</td>'
                f'<td style="{_CELL}">{money(h.company.market_cap)}</td>'
                f'<td style="{_CELL}">{h.days_in_band}</td>'
                "</tr>"
            )
        parts.append("</table>")

    if failed:
        parts.append(
            f'<p style="color:{RED};margin-top:12px">Could not load: '
            + escape(", ".join(o.ticker for o in failed)) + "</p>"
        )
    parts.append(
        f'<p style="color:{GREY};font-size:12px;margin-top:16px">Daily closes from Yahoo Finance; company list '
        f"from Nasdaq (US-based common stocks, no SPACs/funds). Came from = where the close was "
        f"{config.DIRECTION_LOOKBACK} trading days ago. Days in band = trading days in a row within "
        f"±{config.BAND_PCT:g}%. Volume = {config.VOLUME_AVG_PERIOD}-day average.</p></div>"
    )
    return "".join(parts)
