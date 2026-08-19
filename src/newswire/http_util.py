import logging

import requests
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from . import config

logger = logging.getLogger("newswire.http")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        if response is None:
            return True
        return response.status_code == 429 or response.status_code >= 500
    return False


def new_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    return session


@retry(
    reraise=True,
    stop=stop_after_attempt(config.HTTP_MAX_ATTEMPTS),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception(_is_retryable),
)
def get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", config.HTTP_TIMEOUT_SECONDS)
    response = session.get(url, **kwargs)
    response.raise_for_status()
    return response
