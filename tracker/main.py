"""Entry point: run all enabled checkers, diff against last-seen state,
push notifications for products with alerts on, and hand newly-buyable
purchase-flagged products to auto-checkout when it's enabled."""

import os
import sys

from .checkers import CHECKERS
from .config import load_config
from .httpx import make_session
from .models import Hit
from .notify import notify_info, notify_new_listing, notify_stock
from .state import load_state, now, save_state

DAY = 24 * 3600


def process_hits(cfg: dict, state: dict, hits: list[Hit],
                 products_by_id: dict) -> list[tuple[Hit, dict]]:
    """Update state, send notifications for alert-enabled products; return
    (hit, product) pairs that just became buyable AND are purchase-flagged."""
    to_buy = []
    listings = state["listings"]
    for hit in hits:
        product = products_by_id.get(hit.product_id)
        alert = product.get("alert", True) if product else True
        prev = listings.get(hit.key)
        newly_buyable = hit.in_stock and (prev is None or not prev.get("in_stock"))

        if alert:
            if newly_buyable:
                notify_stock(cfg, hit)
            elif prev is None and not hit.in_stock:
                notify_new_listing(cfg, hit)
        if newly_buyable and product and product.get("purchase"):
            to_buy.append((hit, product))

        listings[hit.key] = {
            "title": hit.title,
            "product": hit.product_id,
            "in_stock": hit.in_stock,
            "status": hit.status,
            "price": hit.price,
            "last_seen": now(),
        }
    return to_buy


def track_blocks(cfg: dict, state: dict, retailer: str, blocked: bool) -> None:
    blocks = state["blocks"]
    if not blocked:
        blocks.pop(retailer, None)
        return
    entry = blocks.setdefault(retailer, {"since": now(), "last_notified": 0})
    persistent = now() - entry["since"] > DAY
    stale_notice = now() - entry["last_notified"] > DAY
    if persistent and stale_notice and cfg["notifications"].get("notify_on_persistent_block"):
        notify_info(cfg, f"{retailer} has been blocking checks for 24h+",
                    "Stock checks for this retailer aren't getting through. "
                    "Consider adding a direct product URL to watch_urls or "
                    "checking manually.")
        entry["last_notified"] = now()


def main() -> int:
    cfg = load_config()

    if os.environ.get("SEND_TEST_NOTIFICATION", "").lower() == "true":
        sent = notify_info(cfg, "Test notification — tracker is connected",
                           "Your phone will get an urgent push the moment an "
                           f"alert-enabled {cfg['set']['name']} product is buyable.")
        print("Test notification sent — check your phone" if sent
              else "Test notification NOT sent — see the [notify] line above")

    state = load_state()
    session = make_session()
    products_by_id = {p["id"]: p for p in cfg["products"]}
    to_buy: list[tuple[Hit, dict]] = []

    for name, checker in CHECKERS.items():
        if not cfg["retailers"].get(name, {}).get("enabled", False):
            continue
        result = checker(session, cfg)
        flags = []
        if result.blocked:
            flags.append("BLOCKED")
        if result.error:
            flags.append(f"error: {result.error}")
        print(f"[{result.retailer}] {len(result.hits)} matching listing(s)"
              + (f" ({'; '.join(flags)})" if flags else ""))
        for h in result.hits:
            print(f"    {'✔ BUYABLE' if h.in_stock else '  not buyable'} "
                  f"[{h.product_id}] [{h.status}] {h.title} {h.price} — {h.url}")
        track_blocks(cfg, state, result.retailer, result.blocked)
        to_buy += process_hits(cfg, state, result.hits, products_by_id)

    save_state(state)

    if to_buy and cfg.get("auto_checkout", {}).get("enabled") \
            and os.environ.get("ENABLE_AUTO_CHECKOUT", "").lower() == "true":
        from .checkout.runner import run_checkout
        for hit, product in to_buy:
            run_checkout(cfg, hit, product)

    return 0


if __name__ == "__main__":
    sys.exit(main())
