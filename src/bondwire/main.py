import logging
import os
import sys
import traceback

from . import config, email_send, render, state
from .models import FetchResult, YieldPoint
from .sources import cnbc
from .sources import official

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("bondwire.main")


def _safe(name: str, fn) -> FetchResult:
    try:
        points = fn()
        return FetchResult(name, ok=True, points=points)
    except Exception as exc:  # noqa: BLE001 - isolation boundary
        logger.error("Source %s failed: %s\n%s", name, exc, traceback.format_exc())
        return FetchResult(name, ok=False, points=[], error=str(exc))


def _merge(
    cnbc_res: FetchResult, official_results: dict[str, FetchResult]
) -> tuple[list[YieldPoint], list[YieldPoint]]:
    """CNBC wins for any (country, tenor) it provides. Official points fill the
    gaps and always supply the euro-area row. Returns (points_for_table,
    official_reference_points_not_in_table)."""
    table: dict[tuple[str, str], YieldPoint] = {}
    for p in cnbc_res.points:
        table[p.key] = p

    official_all: list[YieldPoint] = []
    for res in official_results.values():
        official_all.extend(res.points)

    reference: list[YieldPoint] = []
    for p in official_all:
        if p.country == config.EURO_AREA_CODE or p.key not in table:
            table.setdefault(p.key, p)
        else:
            reference.append(p)
    return list(table.values()), reference


def run() -> int:
    cnbc_res = _safe("CNBC", lambda: cnbc.fetch(config.COUNTRIES, config.TENORS))
    if cnbc_res.ok:
        logger.info("CNBC: %d point(s)", len(cnbc_res.points))
    else:
        logger.warning("CNBC FAILED (%s)", cnbc_res.error)

    official_results = {
        name: _safe(name, fn) for name, fn in official.FETCHERS.items()
    }
    for name, res in official_results.items():
        logger.info("%s: %s", name, f"{len(res.points)} pts" if res.ok else f"FAILED {res.error}")

    points, reference = _merge(cnbc_res, official_results)
    all_results = {"CNBC": cnbc_res, **official_results}

    if not points:
        logger.error("No yield data from any source; failing the run.")
        _write_summary(all_results, points, email_sent=False)
        return 1

    prev = state.load()
    subject, text_body, html_body = render.build(points, reference, all_results, prev)
    email_ok = email_send.send(subject, text_body, html_body)

    if email_ok:
        state.save(points)

    _write_summary(all_results, points, email_sent=email_ok)

    if not email_ok:
        logger.error("Email delivery failed; failing the run so GitHub notifies.")
        return 1
    return 0


def _write_summary(results: dict[str, FetchResult], points, email_sent: bool) -> None:
    lines = ["# Bondwire run summary", "", "| Source | Status | Points |", "|---|---|---|"]
    for name, res in results.items():
        status = "OK" if res.ok else f"FAILED: {res.error}"
        lines.append(f"| {name} | {status} | {len(res.points)} |")
    lines += ["", f"Yield points in digest: {len(points)}", f"Email sent: {'yes' if email_sent else 'no'}"]
    text = "\n".join(lines) + "\n"
    try:
        print(text)
    except UnicodeEncodeError:  # narrow local consoles; CI stdout is UTF-8
        print(text.encode("ascii", "replace").decode("ascii"))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)


if __name__ == "__main__":
    sys.exit(run())
