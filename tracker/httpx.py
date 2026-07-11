"""Shared HTTP session with browser-like headers.

Plain, honest requests — no fingerprint spoofing beyond a normal UA string.
Retailers that hard-block scripted traffic will show up as blocked=True and
that's expected; direct watch_urls + the push notification are the fallback.
"""

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

BLOCK_MARKERS = (
    "captcha", "are you a human", "robot or human", "access denied",
    "request unsuccessful", "pardon our interruption",
)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s


def looks_blocked(resp: requests.Response) -> bool:
    if resp.status_code in (403, 429, 503):
        return True
    snippet = resp.text[:4000].lower()
    return any(m in snippet for m in BLOCK_MARKERS)
