"""Pull official 30th Celebration product images from pokemon.com's
product gallery into docs/img/<product-id>.png.

Runs on a GitHub Actions runner (this repo's sandbox blocks outbound
traffic). Defensive by design: if the page yields no '30th' products, it
logs a sample of what it did see and exits 0 so we can adjust the parsing.
"""

import io
import re
import sys

import requests
from PIL import Image

GALLERY = "https://www.pokemon.com/us/pokemon-tcg/product-gallery"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}

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


def harvest(html: str) -> list[tuple[str, str]]:
    """(name, image-url) candidates from IMG tags and embedded JSON."""
    pairs = []
    for m in re.finditer(r"<img[^>]*>", html):
        tag = m.group(0)
        src = re.search(r'(?:data-)?src="([^"]+)"', tag)
        alt = re.search(r'alt="([^"]*)"', tag)
        if src and "assets.pokemon.com" in src.group(1):
            pairs.append((alt.group(1) if alt else "", src.group(1)))
    json_like = [
        r'"name"\s*:\s*"([^"]+)"[^{}]*?"(?:image|imageUrl|thumbnail)[^"]*"\s*:\s*"([^"]+)"',
        r'"(?:image|imageUrl|thumbnail)[^"]*"\s*:\s*"([^"]+)"[^{}]*?"name"\s*:\s*"([^"]+)"',
    ]
    for m in re.finditer(json_like[0], html):
        pairs.append((m.group(1), m.group(2)))
    for m in re.finditer(json_like[1], html):
        pairs.append((m.group(2), m.group(1)))
    return pairs


def main() -> int:
    pairs: list[tuple[str, str]] = []
    for page in range(1, 7):
        url = GALLERY if page == 1 else f"{GALLERY}?page={page}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
        except requests.RequestException as e:
            print(f"page {page}: request failed: {type(e).__name__}")
            continue
        print(f"page {page}: HTTP {r.status_code}, {len(r.text)} bytes")
        if r.status_code != 200:
            continue
        pairs += harvest(r.text)

    # dedupe on url
    seen, unique = set(), []
    for n, u in pairs:
        if u not in seen:
            seen.add(u)
            unique.append((n, u))

    thirty = [(n, u) for n, u in unique if "30th" in n.lower()]
    print(f"{len(unique)} unique product images found, {len(thirty)} mention '30th'")
    if not thirty:
        print("No 30th products found. Sample of names seen:")
        for n, _ in unique[:40]:
            print("  -", (n or "(no alt)")[:110])
        return 0

    print("All '30th' product names:")
    for n, _ in thirty:
        print("  *", n[:110])

    saved = 0
    for pid, kws in KEYWORDS.items():
        match = next(((n, u) for n, u in thirty
                      if any(k in n.lower() for k in kws)), None)
        if not match:
            print(f"{pid}: no gallery match yet")
            continue
        name, url = match
        if url.startswith("//"):
            url = "https:" + url
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            img.thumbnail((800, 800))
            img.save(f"docs/img/{pid}.png")
            print(f"saved docs/img/{pid}.png  <-  {name}")
            saved += 1
        except Exception as e:  # noqa: BLE001
            print(f"{pid}: download failed: {type(e).__name__}: {e}")
    print("total saved:", saved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
