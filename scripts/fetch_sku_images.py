"""Pull official 30th Celebration product images from pokemon.com's
product gallery into docs/img/<product-id>.png.

The gallery is a client-rendered SPA, so this drives headless Chromium
(Playwright) on a GitHub Actions runner, searches for "30th", and scrapes
the rendered tiles. Defensive by design: when nothing matches it logs what
it did see (tile names + JSON endpoints the page called) so parsing can be
tuned, and exits 0.
"""

import io
import sys

import requests
from PIL import Image
from playwright.sync_api import sync_playwright

GALLERY = "https://www.pokemon.com/us/pokemon-tcg/product-gallery"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

KEYWORDS = {
    "elite-trainer-box": ["elite trainer box"],
    "ultra-premium-collection": ["ultra-premium", "ultra premium"],
    "premium-figure-collection": ["figure collection"],
    "collector-chest": ["collector chest", "collector's chest"],
    "pin-collection": ["pin collection"],
    "mini-tin": ["mini tin"],
    "poster-collection": ["poster collection"],
    "booster-bundle": ["booster bundle"],
}

COLLECT_JS = """els => els.map(e => ({
    text: ((e.closest('a,li,article,section,div') || {}).innerText || '').trim().slice(0, 160),
    alt: e.alt || '',
    src: e.currentSrc || e.src || e.getAttribute('data-src') || ''
}))"""


def main() -> int:
    tiles, api_urls = [], set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(user_agent=UA)
        page.on("response", lambda r: api_urls.add(r.url)
                if "json" in (r.headers.get("content-type") or "") else None)

        page.goto(GALLERY, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(6_000)

        # Try the gallery's own search first — most direct route to the set
        try:
            search = page.locator(
                'input[type="search"], input[placeholder*="search" i], '
                'input[name*="search" i]').first
            if search.count():
                search.fill("30th")
                search.press("Enter")
                page.wait_for_timeout(4_000)
                tiles += page.eval_on_selector_all("img", COLLECT_JS)
                print(f"after search: {len(tiles)} img nodes")
        except Exception as e:  # noqa: BLE001
            print("search attempt failed:", type(e).__name__)

        # Scroll / load-more sweep for good measure
        for _ in range(6):
            tiles += page.eval_on_selector_all("img", COLLECT_JS)
            try:
                more = page.locator(
                    'button:has-text("Load More"), a:has-text("Load More")').first
                if more.count():
                    more.click(timeout=3_000)
                    page.wait_for_timeout(2_500)
                else:
                    page.mouse.wheel(0, 4_000)
                    page.wait_for_timeout(1_200)
            except Exception:  # noqa: BLE001
                break
        browser.close()

    seen, unique = set(), []
    for t in tiles:
        src = t["src"]
        if src and src not in seen and "assets.pokemon.com" in src:
            seen.add(src)
            unique.append(t)

    print(f"{len(unique)} unique assets.pokemon.com images")
    print("JSON endpoints the page called (for future tuning):")
    for u in sorted(api_urls)[:20]:
        print("   ", u[:170])

    thirty = [t for t in unique if "30th" in (t["text"] + " " + t["alt"]).lower()]
    print(f"{len(thirty)} tiles mention '30th'")
    if not thirty:
        print("Sample of tile texts seen:")
        for t in unique[:40]:
            print("  -", (t["text"] or t["alt"] or "(none)")[:110].replace("\n", " / "))
        return 0

    print("All '30th' tiles:")
    for t in thirty:
        print("  *", (t["text"] or t["alt"])[:110].replace("\n", " / "))

    saved = 0
    for pid, kws in KEYWORDS.items():
        label = lambda t: (t["text"] + " " + t["alt"]).lower()  # noqa: E731
        match = next((t for t in thirty if any(k in label(t) for k in kws)), None)
        if not match:
            print(f"{pid}: no gallery match yet")
            continue
        url = match["src"]
        if url.startswith("//"):
            url = "https:" + url
        try:
            resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            img.thumbnail((800, 800))
            img.save(f"docs/img/{pid}.png")
            print(f"saved docs/img/{pid}.png  <-  {(match['text'] or match['alt'])[:90]}")
            saved += 1
        except Exception as e:  # noqa: BLE001
            print(f"{pid}: download failed: {type(e).__name__}: {e}")
    print("total saved:", saved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
