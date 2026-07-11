"""Best-effort automated checkout (Playwright).

Honest expectations, spelled out:
  * This drives a normal Chromium browser with no captcha-solving or
    bot-detection evasion. If the retailer challenges the session, the run
    stops and you get a push notification so YOU can buy manually — the
    stock alert with a direct link is always the reliable path.
  * Most retailers' terms of service prohibit automated purchasing; orders
    can be cancelled and accounts actioned. This is off by default and only
    runs when you set ENABLE_AUTO_CHECKOUT=true plus credentials.
  * Dry-run by default: without CONFIRM_PURCHASE=true it walks to the order
    review step, stops, and notifies you — it never places the order.

Credentials come from environment variables (GitHub repo secrets):
  Pokémon Center: PC_EMAIL, PC_PASSWORD
  Target:         TARGET_EMAIL, TARGET_PASSWORD
Payment/shipping must already be saved on the retailer account; these flows
never type card numbers.
"""

import os

from ..models import Hit
from ..notify import notify_info

RETAILER_KEYS = {
    "Pokémon Center": "pokemoncenter",
    "Target": "target",
}

CRED_ENV = {
    "pokemoncenter": ("PC_EMAIL", "PC_PASSWORD"),
    "target": ("TARGET_EMAIL", "TARGET_PASSWORD"),
}


def _price_ok(cfg: dict, hit: Hit, product: dict | None = None) -> bool:
    cap = (product or {}).get("max_price_usd") or cfg["auto_checkout"].get("max_price_usd")
    if not cap or not hit.price:
        return True
    digits = "".join(c for c in hit.price if c.isdigit() or c == ".")
    try:
        return float(digits) <= float(cap)
    except ValueError:
        return True


def run_checkout(cfg: dict, hit: Hit, product: dict) -> None:
    if not product.get("purchase"):
        print(f"[checkout] {product.get('id')}: purchase flag off, skipping")
        return
    key = RETAILER_KEYS.get(hit.retailer)
    if key not in (cfg["auto_checkout"].get("retailers") or []):
        print(f"[checkout] {hit.retailer}: auto-checkout not configured, skipping")
        return
    env_user, env_pass = CRED_ENV[key]
    email, password = os.environ.get(env_user), os.environ.get(env_pass)
    if not email or not password:
        print(f"[checkout] {hit.retailer}: missing {env_user}/{env_pass} secrets, skipping")
        return
    if not _price_ok(cfg, hit, product):
        notify_info(cfg, f"Skipped auto-checkout at {hit.retailer}",
                    f"Price {hit.price} exceeds max_price_usd cap.\n{hit.url}")
        return

    confirm = os.environ.get("CONFIRM_PURCHASE", "").lower() == "true"
    try:
        if key == "pokemoncenter":
            from .pokemoncenter import checkout
        else:
            from .target import checkout
        outcome = checkout(hit, email, password, confirm=confirm,
                           quantity=int(cfg["auto_checkout"].get("quantity", 1)))
        notify_info(cfg, f"Auto-checkout at {hit.retailer}: {outcome}",
                    f"{hit.title}\n{hit.url}")
        print(f"[checkout] {hit.retailer}: {outcome}")
    except Exception as e:  # noqa: BLE001
        notify_info(cfg, f"Auto-checkout FAILED at {hit.retailer}",
                    f"{e}\n\nBuy manually: {hit.url}")
        print(f"[checkout] {hit.retailer}: failed: {e}")
