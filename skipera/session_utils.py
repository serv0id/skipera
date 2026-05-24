import random
import time

import requests

_CSRF_COOKIE_MAP = {
    "CSRF3-Token": "x-csrf3-token",
    "CSRF2-Token": "x-csrf2-token",
    "csrftoken": "x-csrftoken",
}


def get_csrf_headers(session: requests.Session) -> dict[str, str]:
    """Read CSRF tokens from session cookies and return them as per-request headers."""
    headers = {}
    for cookie_name, header_name in _CSRF_COOKIE_MAP.items():
        if cookie_name in session.cookies:
            headers[header_name] = session.cookies[cookie_name]
    return headers


def random_delay(low: float = 2.0, high: float = 5.0) -> None:
    """Sleep for a random duration between *low* and *high* seconds."""
    delay = random.uniform(low, high)
    time.sleep(delay)
