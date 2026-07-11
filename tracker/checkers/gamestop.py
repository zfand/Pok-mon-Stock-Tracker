"""GameStop checker (Salesforce Commerce Cloud storefront).

Search results give product links; each product page embeds JSON-LD with an
availability field, which is what we key off.
"""

import html as htmllib
import json
import re

import requests

from ..config import match_product, watch_urls_for
from ..httpx import looks_blocked
from ..models import CheckResult, Hit

LINK_RE = re.compile(
    r'<a[^>]*class="[^"]*product-tile-link[^"]*"[^>]*href="(?P<href>[^"]+)"[^>]*>',
)
TITLE_ATTR_RE = re.compile(r'data-product-name="([^"]+)"')
JSONLD_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)

BUYABLE = ("instock", "preorder", "presale", "limitedavailability", "onlineonly")


def _availability_from_product_page(session: requests.Session, url: str) -> tuple[bool, str]:
    r = session.get(url, timeout=25)
    if looks_blocked(r):
        return False, "BLOCKED"
    for m in JSONLD_RE.finditer(r.text):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            offers = node.get("offers") or []
            if isinstance(offers, dict):
                offers = [offers]
            for offer in offers:
                avail = str(offer.get("availability", "")).split("/")[-1].lower()
                if avail:
                    return avail in BUYABLE, avail.upper()
    # Fallback: look at the buy button
    if re.search(r'add to cart|pre-?order now', r.text, re.IGNORECASE):
        return True, "BUTTON_PRESENT"
    return False, "NOT_AVAILABLE"


def check(session: requests.Session, cfg: dict) -> CheckResult:
    result = CheckResult(retailer="GameStop")
    # url -> (title, product)
    candidates: dict[str, tuple[str, dict]] = {}

    try:
        r = session.get("https://www.gamestop.com/search/",
                        params={"q": cfg["set"]["search_query"]}, timeout=25)
        if looks_blocked(r):
            result.blocked = True
        else:
            html = r.text
            names = TITLE_ATTR_RE.findall(html)
            links = [m.group("href") for m in LINK_RE.finditer(html)]
            for i, href in enumerate(links):
                title = htmllib.unescape(names[i]) if i < len(names) else href
                product = match_product(cfg, title)
                if not product:
                    continue
                url = "https://www.gamestop.com" + href if href.startswith("/") else href
                candidates[url] = (title, product)
    except Exception as e:  # noqa: BLE001
        result.error = f"search: {e}"

    for url, product in watch_urls_for(cfg, "gamestop"):
        candidates.setdefault(url, (product["name"], product))

    for url, (title, product) in list(candidates.items())[:8]:  # cap page fetches per run
        try:
            in_stock, status = _availability_from_product_page(session, url)
            if status == "BLOCKED":
                result.blocked = True
                continue
            result.hits.append(Hit("GameStop", title, url, in_stock,
                                   status=status, product_id=product["id"]))
        except Exception as e:  # noqa: BLE001
            result.error = (result.error + "; " if result.error else "") + f"{url}: {e}"
    return result
