import os
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_config() -> dict:
    with open(ROOT / "config.yml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    notif = cfg.setdefault("notifications", {})
    if os.environ.get("NTFY_TOPIC"):
        notif["ntfy_topic"] = os.environ["NTFY_TOPIC"]

    bb = cfg.setdefault("retailers", {}).setdefault("bestbuy", {})
    if os.environ.get("BESTBUY_API_KEY"):
        bb["api_key"] = os.environ["BESTBUY_API_KEY"]

    return cfg


def match_product(cfg: dict, title: str) -> dict | None:
    """Return the product a listing title belongs to, or None."""
    t = title.lower()
    for bad in cfg["set"].get("exclude") or []:
        if bad.lower() in t:
            return None
    for product in cfg["products"]:
        if any(bad.lower() in t for bad in product.get("exclude") or []):
            continue
        if all(any(alt.lower() in t for alt in group)
               for group in product["must_include"]):
            return product
    return None


def watch_urls_for(cfg: dict, retailer_key: str) -> list[tuple[str, dict]]:
    """All (url, product) direct watch URLs configured for a retailer."""
    out = []
    for product in cfg["products"]:
        for url in (product.get("watch_urls") or {}).get(retailer_key, []) or []:
            out.append((url, product))
    return out
