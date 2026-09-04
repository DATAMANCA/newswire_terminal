import logging

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from . import config

logger = logging.getLogger("bondwire.email")


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30))
def _send(subject: str, text_body: str, html_body: str) -> None:
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
        json={
            "from": config.RESEND_FROM_EMAIL,
            "to": [config.RECIPIENT_EMAIL],
            "subject": subject,
            "text": text_body,
            "html": html_body,
        },
        timeout=config.HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def send(subject: str, text_body: str, html_body: str) -> bool:
    if not config.RESEND_API_KEY:
        logger.error("RESEND_API_KEY not set; cannot send.")
        return False

    try:
        _send(subject, text_body, html_body)
        logger.info("Sent bond digest: %s", subject)
        return True
    except Exception:
        logger.exception("Failed to send bond digest after retries.")
        return False
