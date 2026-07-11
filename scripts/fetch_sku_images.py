"""Pull official 30th Celebration product images from pokemon.com's asset
CDN into docs/img/<product-id>.png.

The product gallery itself is a bot-walled SPA (confirmed: even headless
Chromium on an Actions runner gets served a compliance/challenge page, not
the gallery), so this does NOT scrape it. Instead it hits the CDN directly:

    https://www.pokemon.com/static-assets/content-assets/cms2/img/
        trading-card-game/series/incrementals/2026/<slug>/<slug>-169-en.png

For products with a confirmed `gallery_slug` in config.yml, it just
downloads. For products without one, it probes a short list of reasonable
slug guesses and logs (does not assume) any hit — add a confirmed slug to
config.yml once you know it, e.g. from a product's gallery page URL. Every
currently-tracked product has a confirmed slug (verified against
pokemon.com's own product gallery), so CANDIDATES is empty until a new
product gets added to config.yml without one yet.
"""

import io
import sys

import requests
import yaml
from PIL import Image

BASE = ("https://www.pokemon.com/static-assets/content-assets/cms2/img/"
         "trading-card-game/series/incrementals/2026/{slug}/{slug}-169-en.png")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Reasonable slug guesses for products without a confirmed gallery_slug yet.
# Purely candidates — nothing here is assumed to exist until probed. Empty
# for now since every tracked product already has a confirmed slug; add an
# entry here (keyed by product id) if a new product gets added without one.
CANDIDATES: dict[str, list[str]] = {}


def try_download(slug: str, pid: str) -> bool:
    url = BASE.format(slug=slug)
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    except requests.RequestException as e:
        print(f"  {slug}: request failed: {type(e).__name__}")
        return False
    if r.status_code != 200 or "image" not in r.headers.get("content-type", ""):
        print(f"  {slug}: HTTP {r.status_code}, "
              f"content-type={r.headers.get('content-type')}")
        return False
    img = Image.open(io.BytesIO(r.content)).convert("RGBA")
    img.save(f"docs/img/{pid}.png")
    print(f"  {slug}: MATCH — saved docs/img/{pid}.png ({img.size[0]}x{img.size[1]})")
    return True


def main() -> int:
    cfg = yaml.safe_load(open("config.yml", encoding="utf-8"))
    saved, unresolved = 0, []

    for product in cfg["products"]:
        pid = product["id"]
        slug = (product.get("gallery_slug") or "").strip()
        print(f"\n[{pid}]")
        if slug:
            if try_download(slug, pid):
                saved += 1
            else:
                print(f"  confirmed slug '{slug}' did not resolve — asset may have moved")
                unresolved.append(pid)
            continue

        found = False
        for candidate in CANDIDATES.get(pid, []):
            if try_download(candidate, pid):
                print(f"  ^ add this to config.yml as: "
                      f"gallery_slug: \"{candidate}\"")
                saved += 1
                found = True
                break
        if not found:
            print("  no candidate matched — still using generated placeholder art")
            unresolved.append(pid)

    print(f"\ntotal images saved/refreshed: {saved}")
    if unresolved:
        print("still unresolved:", ", ".join(unresolved))
    return 0


if __name__ == "__main__":
    sys.exit(main())
