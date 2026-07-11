"""Target checker via the redsky API used by target.com itself."""

import re
import uuid

import requests

from ..config import match_product, watch_urls_for
from ..models import CheckResult, Hit

# Public key embedded in target.com's frontend bundle
KEY = "9f36aeafbe60771e321a7cc95a78140772ab3e96"
SEARCH_URL = "https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v2"
FULFILL_URL = "https://redsky.target.com/redsky_aggregations/v1/web/product_summary_with_fulfillment_v1"


def _tcin_from_url(url: str) -> str | None:
    m = re.search(r"/A-(\d+)", url)
    return m.group(1) if m else None


def check(session: requests.Session, cfg: dict) -> CheckResult:
    result = CheckResult(retailer="Target")
    visitor = uuid.uuid4().hex.upper()
    candidates: dict[str, Hit] = {}  # tcin -> Hit (availability filled in later)

    try:
        r = session.get(SEARCH_URL, params={
            "key": KEY,
            "channel": "WEB",
            "keyword": cfg["set"]["search_query"],
            "count": 24,
            "offset": 0,
            "page": "/s/" + cfg["set"]["search_query"].replace(" ", "+"),
            "pricing_store_id": "3991",
            "visitor_id": visitor,
        }, timeout=20)
        r.raise_for_status()
        products = (r.json().get("data", {}).get("search", {})
                    .get("products", []))
        for p in products:
            item = p.get("item", {})
            title = (item.get("product_description", {}) or {}).get("title", "")
            product = match_product(cfg, title) if title else None
            if not product:
                continue
            tcin = str(p.get("tcin", ""))
            url = (item.get("enrichment", {}) or {}).get("buy_url") or \
                f"https://www.target.com/p/-/A-{tcin}"
            price = (p.get("price", {}) or {}).get("formatted_current_price", "")
            candidates[tcin] = Hit("Target", title, url, in_stock=False,
                                   price=price, product_id=product["id"])
    except Exception as e:  # noqa: BLE001 - checker must not kill the run
        result.error = f"search: {e}"

    for url, product in watch_urls_for(cfg, "target"):
        tcin = _tcin_from_url(url)
        if tcin and tcin not in candidates:
            candidates[tcin] = Hit("Target", product["name"], url,
                                   in_stock=False, product_id=product["id"])

    if not candidates:
        return result

    try:
        r = session.get(FULFILL_URL, params={
            "key": KEY,
            "tcins": ",".join(candidates.keys()),
            "store_id": "3991",
            "pricing_store_id": "3991",
            "visitor_id": visitor,
        }, timeout=20)
        r.raise_for_status()
        for summary in (r.json().get("data", {}).get("product_summaries", []) or []):
            tcin = str(summary.get("tcin", ""))
            hit = candidates.get(tcin)
            if not hit:
                continue
            shipping = ((summary.get("fulfillment", {}) or {})
                        .get("shipping_options", {}) or {})
            status = shipping.get("availability_status", "UNKNOWN")
            hit.status = status
            hit.in_stock = status in ("IN_STOCK", "PRE_ORDER_SELLABLE", "LIMITED_STOCK")
    except Exception as e:  # noqa: BLE001
        result.error = (result.error + "; " if result.error else "") + f"fulfillment: {e}"

    result.hits = list(candidates.values())
    return result
