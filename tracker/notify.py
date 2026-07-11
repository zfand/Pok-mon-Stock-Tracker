import requests

from .models import Hit


def _post(cfg: dict, title: str, body: str, *, priority: str = "default",
          tags: str = "", click: str = "") -> bool:
    """Send a push; returns True only if ntfy accepted it."""
    notif = cfg["notifications"]
    topic = (notif.get("ntfy_topic") or "").strip()
    if not topic:
        print(f"[notify] SKIPPED — no ntfy topic configured "
              f"(set the NTFY_TOPIC repo secret): {title}")
        return False
    url = f"{notif['ntfy_server'].rstrip('/')}/{topic}"
    headers = {"Title": title.encode("utf-8"), "Priority": priority}
    if tags:
        headers["Tags"] = tags
    if click:
        headers["Click"] = click
    try:
        resp = requests.post(url, data=body.encode("utf-8"), headers=headers,
                             timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        # Deliberately terse: exception text can contain the topic-bearing
        # URL, and these lines land in world-readable Actions logs once the
        # repo is public. Never print str(e) or the URL here.
        status = getattr(getattr(e, "response", None), "status_code", None)
        print(f"[notify] push FAILED ({type(e).__name__}, "
              f"HTTP {status or 'n/a'}): {title}")
        return False


def notify_stock(cfg: dict, hit: Hit) -> None:
    price = f" — {hit.price}" if hit.price else ""
    _post(
        cfg,
        title=f"IN STOCK at {hit.retailer}{price}",
        body=f"{hit.title}\n\nTap to open the product page NOW:\n{hit.url}",
        priority="urgent",
        tags="rotating_light,shopping_cart",
        click=hit.url,
    )


def notify_new_listing(cfg: dict, hit: Hit) -> None:
    """A SKU was spotted at a retailer for the first time — sent regardless
    of the product's alert flag, since discovering a listing exists is
    useful even for products that don't get urgent buyability pings.

    Alert-enabled products skip this when they're already buyable (they get
    notify_stock's urgent push instead — see process_hits), so the
    in_stock=True wording here only actually fires for alert-off products.
    """
    price = f" — {hit.price}" if hit.price else ""
    if hit.in_stock:
        title = f"New listing spotted at {hit.retailer} — already buyable!{price}"
        tags = "eyes,shopping_cart"
    else:
        title = f"New listing spotted at {hit.retailer} (not buyable yet)"
        tags = "eyes"
    _post(
        cfg,
        title=title,
        body=f"{hit.title}\nStatus: {hit.status or 'unavailable'}\n{hit.url}",
        priority="high",
        tags=tags,
        click=hit.url,
    )


def notify_info(cfg: dict, title: str, body: str) -> bool:
    return _post(cfg, title=title, body=body, priority="default",
                 tags="information_source")
