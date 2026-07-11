"""Walmart checker: parses the __NEXT_DATA__ JSON embedded in search pages."""

import json
import re

import requests

from ..config import match_product, watch_urls_for
from ..httpx import looks_blocked
from ..models import CheckResult, Hit

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>',
    re.DOTALL,
)


def _extract_items(html: str) -> list[dict]:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return []
    data = json.loads(m.group(1))
    stacks = (data.get("props", {}).get("pageProps", {})
              .get("initialData", {}).get("searchResult", {})
              .get("itemStacks", []))
    items: list[dict] = []
    for stack in stacks:
        items.extend(stack.get("items", []) or [])
    return items


def check(session: requests.Session, cfg: dict) -> CheckResult:
    result = CheckResult(retailer="Walmart")
    try:
        r = session.get("https://www.walmart.com/search",
                        params={"q": cfg["set"]["search_query"]}, timeout=25)
        if looks_blocked(r):
            result.blocked = True
            return result
        for item in _extract_items(r.text):
            title = item.get("name") or ""
            product = match_product(cfg, title) if title else None
            if not product:
                continue
            path = item.get("canonicalUrl") or ""
            url = "https://www.walmart.com" + path if path.startswith("/") else path
            status = item.get("availabilityStatusV2", {}).get("value") or \
                item.get("availabilityStatusDisplayValue", "")
            price = ""
            price_info = item.get("priceInfo") or {}
            if price_info.get("linePrice"):
                price = price_info["linePrice"]
            in_stock = bool(item.get("canAddToCart")) or status in ("IN_STOCK", "PREORDER")
            result.hits.append(Hit("Walmart", title, url, in_stock, price,
                                   str(status), product_id=product["id"]))
    except Exception as e:  # noqa: BLE001
        result.error = str(e)

    # Direct product pages
    for url, product in watch_urls_for(cfg, "walmart"):
        try:
            r = session.get(url, timeout=25)
            if looks_blocked(r):
                result.blocked = True
                continue
            buyable = '"canAddToCart":true' in r.text or '"availabilityStatus":"IN_STOCK"' in r.text
            result.hits.append(Hit("Walmart", product["name"], url,
                                   in_stock=buyable,
                                   status="IN_STOCK" if buyable else "OUT_OF_STOCK",
                                   product_id=product["id"]))
        except Exception as e:  # noqa: BLE001
            result.error = (result.error + "; " if result.error else "") + f"{url}: {e}"
    return result
