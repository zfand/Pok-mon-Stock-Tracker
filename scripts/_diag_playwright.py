"""One-off diagnostic, not part of the regular pipeline: does headless
Chromium fare differently than plain `requests` on an individual
product-gallery DETAIL page? (We already confirmed the LISTING/search page
blocks even a full browser; this checks whether detail pages are the same
wall or a separate, looser one.) Delete this file once the answer is known.
"""
import re
import sys

from playwright.sync_api import sync_playwright

SLUGS = [
    "30th-celebration-elite-trainer-box",
    "30th-celebration-ultra-premium-collections-day-night",
]
BLOCK_MARKERS = ("administrators have been notified", "captcha", "are you a human",
                 "access denied", "pardon our interruption")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
MONTH_DATE_RE = re.compile(
    r'(January|February|March|April|May|June|July|August|September|October|'
    r'November|December)\s+\d{1,2},?\s+\d{4}')


def main() -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for slug in SLUGS:
            page = browser.new_page(user_agent=UA)
            url = f"https://www.pokemon.com/us/pokemon-tcg/product-gallery/{slug}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(4_000)
                html = page.content()
                blocked = any(m in html.lower() for m in BLOCK_MARKERS)
                m = MONTH_DATE_RE.search(html)
                print(f"{slug}: title={page.title()!r} blocked={blocked} "
                      f"html_len={len(html)} first_date_match={m.group(0) if m else None}")
            except Exception as e:  # noqa: BLE001
                print(f"{slug}: FAILED {type(e).__name__}: {e}")
            page.close()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
