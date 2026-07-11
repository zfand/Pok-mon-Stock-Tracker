"""Cron-run scraper: discovers Pokémon TCG product pages via pokemon.com's
sitemap plus known slugs, and records each one's release date / image /
set grouping into data/gallery.json for a future status-page redesign.

This is a pure data-collection pass — it does NOT touch config.yml or the
live status page. See the tracked task "Refactor status page: release-date
schedule view grouped by set" for what's meant to consume this data next.

Individual product pages (/us/pokemon-tcg/product-gallery/<slug>) are
fetched with headless Chromium, not plain HTTP: a one-off diagnostic
confirmed plain `requests` gets walled on every single one of these pages
(100% block rate across 150 real slugs found via sitemap), while a real
rendered browser loads them fine. This mirrors the product-gallery
*listing* page, which is walled for everyone including headless Chromium —
that surface is not attempted here at all; only individual product pages.
Sitemap discovery is the crawl seed, plus any gallery_slug values already
confirmed in config.yml.
"""

import datetime
import json
import sys
import time

import requests
import yaml
from playwright.sync_api import sync_playwright

from gallery_parse import (
    derive_set_slug, extract_image, extract_jsonld_products, extract_name,
    extract_release_date, is_sitemap_index, looks_blocked, parse_sitemap_locs,
)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

GALLERY_BASE = "https://www.pokemon.com/us/pokemon-tcg/product-gallery/"
SITEMAP_CANDIDATES = [
    "https://www.pokemon.com/sitemap.xml",
    "https://www.pokemon.com/us/sitemap.xml",
]
MAX_CHILD_SITEMAPS = 20
MAX_PRODUCT_PAGES = 80   # each page load takes several seconds via a real browser
PAGE_WAIT_MS = 3_500
RETRY_WAIT_MS = 6_000    # one retry with a longer wait if the first load looks too thin
MIN_HTML_LEN = 5_000


def discover_via_sitemap() -> list[str]:
    """Best-effort: product-gallery slugs found via sitemap.xml. Returns []
    (never raises) if sitemaps are unreachable or empty of relevant URLs —
    the caller falls back to config.yml's known slugs either way."""
    slugs: set[str] = set()
    for url in SITEMAP_CANDIDATES:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
        except requests.RequestException as e:
            print(f"sitemap {url}: request failed: {type(e).__name__}")
            continue
        if r.status_code != 200:
            print(f"sitemap {url}: HTTP {r.status_code}")
            continue
        if is_sitemap_index(r.text):
            children = parse_sitemap_locs(r.text)
            relevant = [u for u in children
                       if "product-gallery" in u or "pokemon-tcg" in u][:MAX_CHILD_SITEMAPS]
            print(f"sitemap {url}: index with {len(children)} children, "
                  f"probing {len(relevant)} likely-relevant one(s)")
            for child in relevant:
                try:
                    cr = requests.get(child, headers=HEADERS, timeout=20)
                except requests.RequestException:
                    continue
                if cr.status_code == 200:
                    for u in parse_sitemap_locs(cr.text):
                        if "/product-gallery/" in u:
                            slugs.add(u.rstrip("/").rsplit("/", 1)[-1])
                time.sleep(0.3)
        else:
            locs = parse_sitemap_locs(r.text)
            for u in locs:
                if "/product-gallery/" in u:
                    slugs.add(u.rstrip("/").rsplit("/", 1)[-1])
            print(f"sitemap {url}: direct urlset, {len(locs)} url(s), "
                  f"{len(slugs)} product-gallery slug(s) so far")
    return sorted(slugs)


def _new_record(slug: str, url: str) -> dict:
    return {
        "slug": slug, "url": url, "name": None,
        "release_date": None, "release_date_raw": None,
        "image": None, "set_slug": None, "set_guessed": None,
        "blocked": False, "error": None,
        "fetched_at": datetime.datetime.now(datetime.timezone.utc)
                                 .isoformat(timespec="seconds"),
    }


def fetch_product_page(browser, slug: str) -> dict:
    url = GALLERY_BASE + slug
    record = _new_record(slug, url)
    page = browser.new_page(user_agent=UA)
    try:
        html = ""
        for wait_ms in (PAGE_WAIT_MS, RETRY_WAIT_MS):
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(wait_ms)
            html = page.content()
            if len(html) >= MIN_HTML_LEN:
                break
            print(f"  {slug}: thin response ({len(html)} bytes) after "
                  f"{wait_ms}ms wait, retrying once" if wait_ms == PAGE_WAIT_MS else
                  f"  {slug}: still thin after retry, giving up")
    except Exception as e:  # noqa: BLE001
        record["error"] = type(e).__name__
        page.close()
        return record
    page.close()

    if looks_blocked(html):
        record["blocked"] = True
        return record
    if len(html) < MIN_HTML_LEN:
        record["error"] = f"thin response ({len(html)} bytes)"
        return record

    products = extract_jsonld_products(html)
    record["name"] = extract_name(html, products)
    record["release_date"], record["release_date_raw"] = extract_release_date(html, products)
    record["image"] = extract_image(html, products)
    record["set_slug"], record["set_guessed"] = derive_set_slug(slug)
    return record


def check_169_theory(records: list[dict]) -> None:
    """Honest, logged-not-assumed check of whether the '-169-' image
    filename suffix we've seen so far is a per-set number or (as originally
    guessed when this suffix was first noticed) an aspect-ratio code."""
    by_set: dict[str, str] = {}
    for r in records:
        if r["image"] and r["set_slug"] not in by_set:
            by_set[r["set_slug"]] = r["image"]
    if len(by_set) < 2:
        print("\n'-169-' theory: fewer than 2 sets have a resolved image "
              "so far — not enough data yet to check.")
        return
    tails = [(s, img.rsplit("-", 1)[-1]) for s, img in list(by_set.items())[:6]]
    print("\n'-169-' theory check across different sets:", tails)
    suffixes = {t[1] for t in tails}
    if len(suffixes) == 1:
        print("-> identical suffix across DIFFERENT sets: supports the "
              "'aspect-ratio code' theory, not a per-set number.")
    else:
        print("-> suffix differs by set: could genuinely encode something "
              "set-specific — worth a closer look, not assumed either way.")


def main() -> int:
    cfg = yaml.safe_load(open("config.yml", encoding="utf-8"))
    seed_slugs = {p["gallery_slug"] for p in cfg["products"] if p.get("gallery_slug")}
    print(f"seed slug(s) from config.yml: {sorted(seed_slugs)}")

    discovered = discover_via_sitemap()
    if not discovered:
        print("sitemap discovery found nothing usable — falling back to "
              "config.yml's seed slugs only. Full-catalog discovery isn't "
              "working right now; logging this rather than pretending "
              "otherwise.")

    all_slugs = sorted(seed_slugs | set(discovered))[:MAX_PRODUCT_PAGES]
    print(f"scanning {len(all_slugs)} product page(s) total "
          f"({len(discovered)} discovered via sitemap, {len(seed_slugs)} seeded, "
          f"capped at {MAX_PRODUCT_PAGES} per run)")

    records = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for i, slug in enumerate(all_slugs):
            rec = fetch_product_page(browser, slug)
            flag = (" BLOCKED" if rec["blocked"]
                    else f" error={rec['error']}" if rec["error"] else "")
            print(f"  [{i + 1}/{len(all_slugs)}] {slug}: "
                  f"release={rec['release_date'] or rec['release_date_raw'] or '?'}, "
                  f"set={rec['set_slug']}{' (guessed)' if rec['set_guessed'] else ''}{flag}")
            records.append(rec)
        browser.close()

    check_169_theory(records)

    records.sort(key=lambda r: (r["release_date"] or "9999-99-99", r["set_slug"] or "", r["slug"]))
    with open("data/gallery.json", "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.datetime.now(datetime.timezone.utc)
                                     .isoformat(timespec="seconds"),
            "products": records,
        }, f, indent=2)
        f.write("\n")

    resolved_dates = sum(1 for r in records if r["release_date"])
    resolved_images = sum(1 for r in records if r["image"])
    blocked = sum(1 for r in records if r["blocked"])
    print(f"\nwrote data/gallery.json: {len(records)} product(s), "
          f"{resolved_dates} with a release date, {resolved_images} with an image, "
          f"{blocked} blocked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
