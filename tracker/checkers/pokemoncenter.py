"""Pokémon Center checker.

pokemoncenter.com sits behind aggressive bot protection (Imperva), so plain
HTTP checks will often come back blocked — that's expected and reported
rather than fought. Direct watch_urls give the best odds; when a check does
get through, product pages embed availability JSON.
"""

import re

import requests

from ..config import match_product, watch_urls_for
from ..httpx import looks_blocked
from ..models import CheckResult, Hit

SEARCH_PRODUCT_RE = re.compile(
    r'"productName"\s*:\s*"(?P<name>[^"]+)"[^}]*?"pdpUrl"\s*:\s*"(?P<url>[^"]+)"')
AVAIL_RE = re.compile(r'"availability"\s*:\s*"(?P<a>[^"]+)"')
BUYABLE = ("instock", "preorder", "presale")


def _product_page(session: requests.Session, url: str) -> tuple[bool, str]:
    r = session.get(url, timeout=25)
    if looks_blocked(r):
        return False, "BLOCKED"
    m = AVAIL_RE.search(r.text)
    if m:
        avail = m.group("a").split("/")[-1].lower()
        return avail in BUYABLE, avail.upper()
    if re.search(r'add to cart|pre-?order', r.text, re.IGNORECASE):
        return True, "BUTTON_PRESENT"
    return False, "NOT_AVAILABLE"


def check(session: requests.Session, cfg: dict) -> CheckResult:
    result = CheckResult(retailer="Pokémon Center")
    query = cfg["set"]["search_query"].replace(" ", "%20")
    # url -> (title, product)
    candidates: dict[str, tuple[str, dict]] = {}

    try:
        r = session.get(f"https://www.pokemoncenter.com/search/{query}", timeout=25)
        if looks_blocked(r):
            result.blocked = True
        else:
            for m in SEARCH_PRODUCT_RE.finditer(r.text):
                name = m.group("name")
                product = match_product(cfg, name)
                if not product:
                    continue
                url = m.group("url")
                if url.startswith("/"):
                    url = "https://www.pokemoncenter.com" + url
                candidates[url] = (name, product)
    except Exception as e:  # noqa: BLE001
        result.error = f"search: {e}"

    for url, product in watch_urls_for(cfg, "pokemoncenter"):
        candidates.setdefault(url, (product["name"], product))

    for url, (title, product) in list(candidates.items())[:8]:
        try:
            in_stock, status = _product_page(session, url)
            if status == "BLOCKED":
                result.blocked = True
                continue
            result.hits.append(Hit("Pokémon Center", title, url, in_stock,
                                   status=status, product_id=product["id"]))
        except Exception as e:  # noqa: BLE001
            result.error = (result.error + "; " if result.error else "") + f"{url}: {e}"
    return result
