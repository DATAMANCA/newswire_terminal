"""Builds the technicals email: subject line plus plain-text and HTML bodies."""

from datetime import datetime
from html import escape

from . import config
from .models import BEARISH, BULLISH, StockResult

GREEN = "#1e8449"
RED = "#c0392b"
GREY = "#666"

_DOT = {BULLISH: "\U0001F7E2", BEARISH: "\U0001F534"}  # green / red circle
_NEUTRAL_DOT = "⚪"  # white circle
_COLOUR = {BULLISH: GREEN, BEARISH: RED}

_CELL = "padding:4px 8px;border-bottom:1px solid #eee;text-align:right;white-space:nowrap"
_HEAD = "padding:4px 8px;border-bottom:2px solid #333;text-align:right;white-space:nowrap"


def _dot(direction: str) -> str:
    return _DOT.get(direction, _NEUTRAL_DOT)


def _signed(v: float | None, digits: int = 1) -> str:
    return "n/a" if v is None else f"{v:+.{digits}f}%"


def _num(v: float | None, digits: int = 0) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def _colour_for(v: float | None) -> str:
    if v is None or abs(v) < 0.05:
        return GREY
    return GREEN if v > 0 else RED


def _premarket_pct(r: StockResult) -> float | None:
    if r.premarket_price is None or not r.snapshot:
        return None
    return (r.premarket_price / r.snapshot.close - 1) * 100


def _ordered(flagged: list[StockResult]) -> list[StockResult]:
    """Most signals first, then the most one-sided (all bullish or all bearish)."""

    def key(r: StockResult):
        net = sum(1 if s.direction == BULLISH else -1 if s.direction == BEARISH else 0 for s in r.signals)
        return (-len(r.signals), -abs(net), r.ticker)

    return sorted(flagged, key=key)


def build(mode: str, results: list[StockResult], now: datetime) -> tuple[str, str, str]:
    ok = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    flagged = _ordered([r for r in ok if r.signals])
    all_signals = [s for r in flagged for s in r.signals]
    bulls = sum(s.direction == BULLISH for s in all_signals)
    bears = sum(s.direction == BEARISH for s in all_signals)
    morning = mode == "morning"

    as_of = max((r.snapshot.as_of for r in ok), default=None)
    as_of_text = as_of.strftime("%a %d %b %Y") if as_of else "n/a"
    label = "pre-market" if morning else "close"
    day = now.strftime("%d %b")

    if all_signals:
        subject = (
            f"Technicals {label} {day}: {len(all_signals)} signals on {len(flagged)} stocks "
            f"({_DOT[BULLISH]}{bulls} {_DOT[BEARISH]}{bears})"
        )
    else:
        subject = f"Technicals {label} {day}: no new signals"

    if morning:
        heading = "Pre-market recap"
        intro = (
            f"Signals from the close of {as_of_text}, with pre-market prices as of "
            f"{now.strftime('%I:%M %p').lstrip('0')} Toronto time."
        )
    else:
        heading = "After the close"
        intro = f"Signals from the close of {as_of_text}."
        if as_of and as_of != now.date() and now.hour >= config.MARKET_CLOSE_HOUR:
            intro += " (No US trading today, so this is the last close.)"

    text = _text(heading, intro, flagged, ok, failed, morning, bulls, bears)
    html = _html(heading, intro, flagged, ok, failed, morning, bulls, bears)
    return subject, text, html


def _text(heading, intro, flagged, ok, failed, morning, bulls, bears) -> str:
    lines = [heading.upper(), intro, ""]
    if flagged:
        lines.append(f"{bulls} bullish, {bears} bearish signal(s) on {len(flagged)} stock(s)")
        lines.append("")
        for r in flagged:
            s = r.snapshot
            head = f"{r.ticker}  ${s.close:,.2f} ({_signed(s.change_pct)})"
            if morning:
                head += f"  pre-market {_signed(_premarket_pct(r))}"
            lines.append(head)
            for sig in r.signals:
                lines.append(f"  [{sig.direction}] {sig.group}: {sig.text}")
            lines.append("")
    else:
        lines += ["No new signals on any stock.", ""]

    lines.append("ALL STOCKS")
    for r in ok:
        s = r.snapshot
        row = (
            f"{r.ticker:<6} ${s.close:>9,.2f} {_signed(s.change_pct):>7} {s.trend:<9} "
            f"RSI {_num(s.rsi):>3}  vs50d {_signed(s.vs_sma_fast_pct):>7}  "
            f"vs200d {_signed(s.vs_sma_slow_pct):>7}  from 52w high {_signed(s.from_year_high_pct):>7}"
        )
        if morning:
            row += f"  pre-market {_signed(_premarket_pct(r))}"
        lines.append(row)
    if failed:
        lines += ["", "Could not load: " + ", ".join(f"{r.ticker} ({r.error})" for r in failed)]
    return "\n".join(lines) + "\n"


def _badge(ticker: str) -> str:
    return (
        '<span style="display:inline-block;background:#1f3a93;color:#fff;font-weight:bold;'
        f'padding:2px 8px;border-radius:4px;font-size:14px">{escape(ticker)}</span>'
    )


def _coloured(text: str, colour: str) -> str:
    return f'<span style="color:{colour}">{escape(text)}</span>'


def _html(heading, intro, flagged, ok, failed, morning, bulls, bears) -> str:
    parts = [
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#000;max-width:900px">',
        f'<h2 style="margin:0 0 4px">{escape(heading)}</h2>',
        f'<p style="margin:0 0 12px;color:{GREY}">{escape(intro)}</p>',
    ]

    if flagged:
        parts.append(
            f'<p style="margin:0 0 12px"><b>{_DOT[BULLISH]} {bulls} bullish &nbsp; '
            f"{_DOT[BEARISH]} {bears} bearish</b> signal(s) on {len(flagged)} stock(s)</p>"
        )
        for r in flagged:
            s = r.snapshot
            head = (
                f"{_badge(r.ticker)} &nbsp;<b>${s.close:,.2f}</b> "
                f"{_coloured(_signed(s.change_pct), _colour_for(s.change_pct))}"
                f' &nbsp;<span style="color:{GREY}">{escape(s.trend)}, RSI {_num(s.rsi)}</span>'
            )
            if morning:
                pm = _premarket_pct(r)
                head += f" &nbsp;pre-market {_coloured(_signed(pm), _colour_for(pm))}"
            parts.append(f'<div style="margin:0 0 14px"><div style="margin-bottom:4px">{head}</div>')
            parts.append('<table style="border-collapse:collapse;margin-left:6px">')
            for sig in r.signals:
                colour = _COLOUR.get(sig.direction, GREY)
                parts.append(
                    f'<tr><td style="padding:2px 6px 2px 0;vertical-align:top">{_dot(sig.direction)}</td>'
                    f'<td style="padding:2px 8px 2px 0;color:{GREY};vertical-align:top">{escape(sig.group)}</td>'
                    f'<td style="padding:2px 0;color:{colour}">{escape(sig.text)}</td></tr>'
                )
            parts.append("</table></div>")
    else:
        parts.append('<p style="margin:0 0 12px"><b>No new signals on any stock.</b></p>')

    cols = ["Ticker", "Close", "Day"] + (["Pre-mkt"] if morning else []) + [
        "Trend", "RSI", "MACD", "vs 50d", "vs 200d", "Bollinger %B", "Stoch", "From 52w high",
    ]
    parts.append('<h3 style="margin:20px 0 6px">All stocks</h3>')
    parts.append('<table style="border-collapse:collapse;font-size:13px">')
    parts.append(
        "<tr>"
        + "".join(
            f'<th style="{_HEAD}{";text-align:left" if c in ("Ticker", "Trend") else ""}">{c}</th>' for c in cols
        )
        + "</tr>"
    )
    for r in ok:
        s = r.snapshot
        rsi_colour = (
            RED if s.rsi is not None and s.rsi >= config.RSI_OVERBOUGHT
            else GREEN if s.rsi is not None and s.rsi <= config.RSI_OVERSOLD
            else "#000"
        )
        trend_colour = {"Uptrend": GREEN, "Downtrend": RED}.get(s.trend, GREY)
        macd = "n/a" if s.macd_above_signal is None else ("above signal" if s.macd_above_signal else "below signal")
        macd_colour = GREY if s.macd_above_signal is None else (GREEN if s.macd_above_signal else RED)
        cells = [
            f'<td style="{_CELL};text-align:left"><b>{escape(r.ticker)}</b></td>',
            f'<td style="{_CELL}">${s.close:,.2f}</td>',
            f'<td style="{_CELL};color:{_colour_for(s.change_pct)}">{_signed(s.change_pct)}</td>',
        ]
        if morning:
            pm = _premarket_pct(r)
            cells.append(f'<td style="{_CELL};color:{_colour_for(pm)}">{_signed(pm)}</td>')
        cells += [
            f'<td style="{_CELL};text-align:left;color:{trend_colour}">{s.trend}</td>',
            f'<td style="{_CELL};color:{rsi_colour}">{_num(s.rsi)}</td>',
            f'<td style="{_CELL};color:{macd_colour}">{macd}</td>',
            f'<td style="{_CELL};color:{_colour_for(s.vs_sma_fast_pct)}">{_signed(s.vs_sma_fast_pct)}</td>',
            f'<td style="{_CELL};color:{_colour_for(s.vs_sma_slow_pct)}">{_signed(s.vs_sma_slow_pct)}</td>',
            f'<td style="{_CELL}">{_num(None if s.bollinger_pct_b is None else s.bollinger_pct_b * 100)}</td>',
            f'<td style="{_CELL}">{_num(s.stoch_k)}</td>',
            f'<td style="{_CELL}">{_signed(s.from_year_high_pct)}</td>',
        ]
        parts.append("<tr>" + "".join(cells) + "</tr>")
    parts.append("</table>")

    if failed:
        parts.append(
            f'<p style="color:{RED};margin-top:12px">Could not load: '
            + escape(", ".join(f"{r.ticker} ({r.error})" for r in failed))
            + "</p>"
        )

    parts.append(
        f'<p style="color:{GREY};font-size:12px;margin-top:16px">Daily candles from Yahoo Finance. '
        f"RSI {config.RSI_PERIOD} ({config.RSI_OVERBOUGHT}/{config.RSI_OVERSOLD}), "
        f"MACD {config.MACD_FAST}/{config.MACD_SLOW}/{config.MACD_SIGNAL}, "
        f"Bollinger {config.BOLLINGER_PERIOD}/{config.BOLLINGER_STDDEV:g} "
        "(%B: 0 = lower band, 100 = upper band), "
        f"Stochastic {config.STOCH_PERIOD}/{config.STOCH_SMOOTH}/{config.STOCH_SIGNAL}. "
        f"Divergences are confirmed {config.DIVERGENCE_PIVOT_WINDOW} days after the swing point. "
        "Signals are alerts, not advice.</p>"
    )
    parts.append("</div>")
    return "\n".join(parts)
