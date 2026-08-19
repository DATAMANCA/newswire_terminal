import logging
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from newswire import config, state  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("newswire.watchdog")


def _send_alert(last_run_utc: str | None) -> None:
    if last_run_utc:
        body = f"No successful Newswire Terminal run has been recorded since {last_run_utc}."
    else:
        body = "Newswire Terminal has no recorded successful run at all (state.json missing or empty)."
    body += "\n\nCheck the GitHub Actions tab for the poll.yml workflow."

    message = MIMEText(body)
    message["Subject"] = "Newswire Terminal watchdog: pipeline may be stalled"
    message["From"] = config.GMAIL_ADDRESS
    message["To"] = config.GMAIL_ADDRESS

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=config.HTTP_TIMEOUT_SECONDS) as smtp:
        smtp.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        smtp.send_message(message)


def main() -> int:
    current_state, is_first_run = state.load_state()
    last_run_utc = current_state.get("last_run_utc")

    if is_first_run or not last_run_utc:
        logger.warning("No prior successful run recorded yet; alerting.")
        _send_alert(last_run_utc)
        return 0

    last_run = datetime.fromisoformat(last_run_utc)
    age = datetime.now(timezone.utc) - last_run
    threshold = timedelta(hours=config.WATCHDOG_STALE_THRESHOLD_HOURS)

    if age > threshold:
        logger.warning("Last run was %s ago (threshold %s); alerting.", age, threshold)
        _send_alert(last_run_utc)
    else:
        logger.info("Last run was %s ago; within threshold, no alert.", age)

    return 0


if __name__ == "__main__":
    sys.exit(main())
