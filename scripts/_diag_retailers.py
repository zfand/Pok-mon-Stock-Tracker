"""One-off diagnostic: what do Ace Hardware, Dick's Sporting Goods, and
Barnes & Noble actually serve for a Pokemon TCG search? This sandbox can't
reach these sites directly, so this runs on an Actions runner (real
egress) to find real URL patterns and parsing signals before writing real
checkers. Delete this file (and its temp workflow) once answered.
"""
import re
import sys

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

TARGETS = {
    "Ace Hardware": "https://www.acehardware.com/search?query=pokemon+tcg",
    "Dick's Sporting Goods": "https://www.dickssportinggoods.com/search/SearchDisplay?searchTerm=pokemon+tcg",
    "Dick's Sporting Goods (alt)": "https://www.dickssportinggoods.com/search?searchTerm=pokemon+tcg",
    "Barnes & Noble": "https://www.barnesandnoble.com/s/pokemon%20tcg",
}

JSONLD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def probe(name: str, url: str) -> None:
    print(f"\n=== {name} ===")
    print(f"URL: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
    except requests.RequestException as e:
        print(f"REQUEST FAILED: {type(e).__name__}: {e}")
        return
    print(f"status={r.status_code}  final_url={r.url}  len={len(r.text)}")
    if r.status_code != 200:
        print("body sample:", r.text[:300].replace("\n", " "))
        return

    html = r.text
    jsonld_blocks = JSONLD_RE.findall(html)
    print(f"json-ld blocks: {len(jsonld_blocks)}")
    for i, block in enumerate(jsonld_blocks[:3]):
        print(f"  [{i}] sample: {block[:200].strip().replace(chr(10), ' ')}")

    has_next_data = bool(NEXT_DATA_RE.search(html))
    print(f"__NEXT_DATA__ present: {has_next_data}")

    lower = html.lower()
    for marker in ("pokemon", "captcha", "access denied", "are you a human",
                   "pardon our interruption", "add to cart", "product-tile",
                   "data-testid", "algolia", "search-results"):
        print(f"  contains {marker!r}: {marker in lower}")

    # crude: any pokemon-related product-ish snippet
    idx = lower.find("pokemon")
    if idx != -1:
        print("context around first 'pokemon' mention:")
        print(" ", html[max(0, idx - 150):idx + 150].replace("\n", " "))


def main() -> int:
    for name, url in TARGETS.items():
        probe(name, url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
