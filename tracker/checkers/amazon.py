"""Amazon checker.

Amazon blocks scripted search traffic aggressively, so this checker only
looks at direct product URLs from watch_urls (add the /dp/ASIN link once a
listing exists). Blocks are reported, not fought.
"""

import re

import requests

from ..config import watch_urls_for
from ..httpx import looks_blocked
from ..models import CheckResult, Hit

TITLE_RE = re.compile(r'<span id="productTitle"[^>]*>\s*(.*?)\s*</span>', re.DOTALL)
PRICE_RE = re.compile(r'"priceToPay"[^}]*?"displayString"\s*:\s*"([^"]+)"')

BUY_SIGNALS = ('id="add-to-cart-button"', 'id="buy-now-button"',
               'id="preOrderButton"', ">Pre-order Now<")
DEAD_SIGNALS = ("Currently unavailable", "We don't know when or if this item "
                "will be back in stock")


def check(session: requests.Session, cfg: dict) -> CheckResult:
    result = CheckResult(retailer="Amazon")
    for url, product in watch_urls_for(cfg, "amazon"):
        try:
            r = session.get(url, timeout=25)
            if looks_blocked(r):
                result.blocked = True
                continue
            html = r.text
            tm = TITLE_RE.search(html)
            title = tm.group(1).strip() if tm else product["name"]
            pm = PRICE_RE.search(html)
            price = pm.group(1) if pm else ""
            if any(s in html for s in DEAD_SIGNALS):
                in_stock, status = False, "UNAVAILABLE"
            elif any(s in html for s in BUY_SIGNALS):
                in_stock, status = True, "BUYABLE"
            else:
                in_stock, status = False, "UNKNOWN"
            result.hits.append(Hit("Amazon", title, url, in_stock, price,
                                   status, product_id=product["id"]))
        except Exception as e:  # noqa: BLE001
            result.error = (result.error + "; " if result.error else "") + f"{url}: {e}"
    return result
