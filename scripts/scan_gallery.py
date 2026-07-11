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
rendered browser succeeded cleanly on an isolated single request. But a
batch of 80 sequential browser requests in one run came back ~99% blocked
— including the very same slug that had just succeeded in isolation minutes
earlier. That's the signature of adaptive, volume-based rate limiting, not
a hard per-page wall: a lone request looks human, a rapid sequence from
one CI IP does not. Respecting that (rather than trying to defeat it with
IP rotation or fingerprint spoofing, which is out of bounds here) means
crawling in small, politely-paced batches — hence the low per-run cap and
long randomized delay below. confirmed gallery_slug values from config.yml
are always scanned first, ahead of sitemap-discovered slugs, so the small
per-run budget goes to already-known products before speculative ones.
"""

import datetime
import json
import random
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
# Kept deliberately small and paced: a batch of 80 back-to-back page loads
# came back ~99% blocked in testing, while a single isolated request
# succeeded cleanly — this is rate-based bot mitigation, not a hard wall,
# so the fix is a gentler pace, not a bigger hammer.
MAX_PRODUCT_PAGES = 12
PAGE_WAIT_MS = 3_500
RETRY_WAIT_MS = 6_000    # one retry with a longer wait if the first load looks too thin
MIN_HTML_LEN = 5_000
MIN_DELAY_BETWEEN_PAGES_SEC = 8
MAX_DELAY_BETWEEN_PAGES_SEC = 16


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


def load_existing_gallery() -> tuple[dict[str, dict], int]:
    """(slug -> record) for everything ever recorded, plus the rotation
    cursor for how far through the non-seed discovery backlog we've gotten.
    Missing/corrupt file just means starting fresh — never fatal."""
    try:
        with open("data/gallery.json", encoding="utf-8") as f:
            data = json.load(f)
        by_slug = {p["slug"]: p for p in data.get("products", [])}
        return by_slug, int(data.get("next_scan_offset", 0))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {}, 0


def main() -> int:
    cfg = yaml.safe_load(open("config.yml", encoding="utf-8"))
    seed_slugs = {p["gallery_slug"] for p in cfg["products"] if p.get("gallery_slug")}
    print(f"seed slug(s) from config.yml: {sorted(seed_slugs)}")

    discovered = discover_via_sitemap()
    if not discovered:
        print("sitemap discovery found nothing usable this run — falling "
              "back to config.yml's seed slugs only for the seed portion of "
              "the budget. Rotation through the previously-discovered "
              "backlog (if any is already on file) still proceeds.")

    existing_by_slug, cursor = load_existing_gallery()

    # Confirmed slugs are re-scanned every run (their release dates matter
    # most and there are only ever a handful). The much larger backlog of
    # sitemap-discovered slugs is worked through a small window at a time,
    # rotating via a persisted cursor, so the whole catalog gets covered
    # over many gentle runs instead of one loud one.
    backlog = sorted((set(discovered) | set(existing_by_slug)) - seed_slugs)
    budget_for_backlog = max(MAX_PRODUCT_PAGES - len(seed_slugs), 0)
    if backlog and budget_for_backlog:
        cursor %= len(backlog)
        window = (backlog[cursor:] + backlog[:cursor])[:budget_for_backlog]
        next_cursor = (cursor + len(window)) % len(backlog)
    else:
        window, next_cursor = [], cursor

    all_slugs = sorted(seed_slugs) + window
    print(f"scanning {len(all_slugs)} product page(s) this run "
          f"({len(seed_slugs)} confirmed seed(s), {len(window)} from a "
          f"backlog of {len(backlog)} discovered-but-not-yet-fresh slugs), "
          f"paced {MIN_DELAY_BETWEEN_PAGES_SEC}-{MAX_DELAY_BETWEEN_PAGES_SEC}s "
          f"apart to stay a polite crawler")

    new_records = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for i, slug in enumerate(all_slugs):
            if i > 0:
                time.sleep(random.uniform(MIN_DELAY_BETWEEN_PAGES_SEC,
                                          MAX_DELAY_BETWEEN_PAGES_SEC))
            rec = fetch_product_page(browser, slug)
            flag = (" BLOCKED" if rec["blocked"]
                    else f" error={rec['error']}" if rec["error"] else "")
            print(f"  [{i + 1}/{len(all_slugs)}] {slug}: "
                  f"release={rec['release_date'] or rec['release_date_raw'] or '?'}, "
                  f"set={rec['set_slug']}{' (guessed)' if rec['set_guessed'] else ''}{flag}")
            new_records.append(rec)
        browser.close()

    check_169_theory(new_records)

    # Merge: this run's results overwrite their slugs; everything else
    # already on file (not touched this run) carries forward unchanged.
    existing_by_slug.update({r["slug"]: r for r in new_records})
    all_records = sorted(existing_by_slug.values(),
                         key=lambda r: (r["release_date"] or "9999-99-99",
                                       r["set_slug"] or "", r["slug"]))

    with open("data/gallery.json", "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.datetime.now(datetime.timezone.utc)
                                     .isoformat(timespec="seconds"),
            "next_scan_offset": next_cursor,
            "products": all_records,
        }, f, indent=2)
        f.write("\n")

    resolved_dates = sum(1 for r in all_records if r["release_date"])
    resolved_images = sum(1 for r in all_records if r["image"])
    blocked = sum(1 for r in all_records if r["blocked"])
    print(f"\nwrote data/gallery.json: {len(all_records)} product(s) total "
          f"(accumulated across all runs), {resolved_dates} with a release "
          f"date, {resolved_images} with an image, {blocked} currently "
          f"marked blocked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
