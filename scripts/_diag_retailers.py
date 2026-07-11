"""Round 2: Playwright-rendered probe. Round 1 (plain requests) found:
Ace Hardware -> Cloudflare "Just a moment..." challenge (403); Dick's ->
200 but an empty client-rendered shell, no JSON-LD, no __NEXT_DATA__;
Barnes & Noble -> 404, wrong URL guess. This checks whether a real browser
gets further, and tries a few more B&N URL patterns.
"""
import re
import sys

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

TARGETS = [
    ("Ace Hardware", "https://www.acehardware.com/search?query=pokemon%20tcg"),
    ("Dick's Sporting Goods", "https://www.dickssportinggoods.com/search?searchTerm=pokemon%20tcg"),
    ("Barnes & Noble /s/ plus", "https://www.barnesandnoble.com/s/pokemon+tcg"),
    ("Barnes & Noble /search/", "https://www.barnesandnoble.com/search/pokemon+tcg"),
    ("Barnes & Noble ?q=", "https://www.barnesandnoble.com/s/pokemon-tcg?q=pokemon+tcg"),
]

JSONLD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)
BLOCK_MARKERS = ("just a moment", "captcha", "are you a human", "access denied",
                 "pardon our interruption", "attention required")


def probe(pw, name: str, url: str) -> None:
    print(f"\n=== {name} ===")
    print(f"URL: {url}")
    browser = pw.chromium.launch()
    page = browser.new_page(user_agent=UA)
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(4_000)
        html = page.content()
        status = resp.status if resp else None
        print(f"http_status={status}  final_url={page.url}  html_len={len(html)}  title={page.title()!r}")
        lower = html.lower()
        blocked = any(m in lower for m in BLOCK_MARKERS)
        print(f"looks blocked: {blocked}")
        jsonld = JSONLD_RE.findall(html)
        print(f"json-ld blocks: {len(jsonld)}")
        for i, block in enumerate(jsonld[:3]):
            print(f"  [{i}] {block[:200].strip().replace(chr(10), ' ')}")
        print(f"contains 'pokemon': {'pokemon' in lower}")
        idx = lower.find("pokemon")
        if idx != -1:
            print("  context:", html[max(0, idx - 150):idx + 150].replace("\n", " "))
        for marker in ("add to cart", "product-tile", "data-testid", "algolia",
                       "no results", "0 results", "sold out"):
            if marker in lower:
                print(f"  contains {marker!r}: True")
    except Exception as e:  # noqa: BLE001
        print(f"FAILED: {type(e).__name__}: {e}")
    finally:
        browser.close()


def main() -> int:
    with sync_playwright() as pw:
        for name, url in TARGETS:
            probe(pw, name, url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
