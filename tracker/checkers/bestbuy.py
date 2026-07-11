"""Best Buy checker.

Preferred path: the official Products API (free key from
https://developer.bestbuy.com, set as repo secret BESTBUY_API_KEY).
Fallback: scrape the search page for add-to-cart button states.
Direct watch_urls are checked as product pages either way.
"""

import re

import requests

from ..config import match_product, watch_urls_for
from ..httpx import looks_blocked
from ..models import CheckResult, Hit

API_URL = "https://api.bestbuy.com/v1/products(search={q})"
BUTTON_RE = re.compile(
    r'data-button-state="(?P<state>[A-Z_]+)"[^>]*data-sku-id="(?P<sku>\d+)"'
)
ANY_BUTTON_RE = re.compile(r'data-button-state="(?P<state>[A-Z_]+)"')
SKU_ITEM_RE = re.compile(
    r'<h4 class="sku-title">\s*<a[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>[^<]+)</a>',
    re.DOTALL,
)
BUYABLE_STATES = ("ADD_TO_CART", "PRE_ORDER")


def _check_api(session: requests.Session, cfg: dict, key: str, result: CheckResult) -> None:
    q = "&search=".join(cfg["set"]["search_query"].split())
    r = session.get(API_URL.format(q=q), params={
        "apiKey": key,
        "format": "json",
        "show": "sku,name,salePrice,onlineAvailability,url,releaseDate",
        "pageSize": 25,
    }, timeout=20)
    r.raise_for_status()
    for p in r.json().get("products", []):
        title = p.get("name", "")
        product = match_product(cfg, title)
        if not product:
            continue
        result.hits.append(Hit(
            "Best Buy", title, p.get("url", ""),
            in_stock=bool(p.get("onlineAvailability")),
            price=f"${p['salePrice']}" if p.get("salePrice") else "",
            status="ONLINE_AVAILABLE" if p.get("onlineAvailability") else "UNAVAILABLE",
            product_id=product["id"],
        ))


def _check_scrape(session: requests.Session, cfg: dict, result: CheckResult) -> None:
    r = session.get("https://www.bestbuy.com/site/searchpage.jsp",
                    params={"st": cfg["set"]["search_query"], "intl": "nosplash"},
                    timeout=25)
    if looks_blocked(r):
        result.blocked = True
        return
    html = r.text
    button_states = {m.group("sku"): m.group("state") for m in BUTTON_RE.finditer(html)}
    for m in SKU_ITEM_RE.finditer(html):
        title = m.group("title").strip()
        product = match_product(cfg, title)
        if not product:
            continue
        href = m.group("href")
        url = "https://www.bestbuy.com" + href if href.startswith("/") else href
        sku_m = re.search(r"/(\d+)\.p", href)
        state = button_states.get(sku_m.group(1), "UNKNOWN") if sku_m else "UNKNOWN"
        result.hits.append(Hit("Best Buy", title, url,
                               in_stock=state in BUYABLE_STATES, status=state,
                               product_id=product["id"]))


def _check_watch_urls(session: requests.Session, cfg: dict, result: CheckResult) -> None:
    for url, product in watch_urls_for(cfg, "bestbuy"):
        try:
            r = session.get(url, timeout=25)
            if looks_blocked(r):
                result.blocked = True
                continue
            m = ANY_BUTTON_RE.search(r.text)
            state = m.group("state") if m else "UNKNOWN"
            result.hits.append(Hit("Best Buy", product["name"], url,
                                   in_stock=state in BUYABLE_STATES, status=state,
                                   product_id=product["id"]))
        except Exception as e:  # noqa: BLE001
            result.error = (result.error + "; " if result.error else "") + f"{url}: {e}"


def check(session: requests.Session, cfg: dict) -> CheckResult:
    result = CheckResult(retailer="Best Buy")
    key = cfg.get("retailers", {}).get("bestbuy", {}).get("api_key")
    try:
        if key:
            _check_api(session, cfg, key, result)
        else:
            _check_scrape(session, cfg, result)
    except Exception as e:  # noqa: BLE001
        result.error = str(e)
    _check_watch_urls(session, cfg, result)
    return result
