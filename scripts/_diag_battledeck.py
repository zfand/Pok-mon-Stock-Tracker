import json
import re
from playwright.sync_api import sync_playwright

URL = "https://www.pokemon.com/us/pokemon-tcg/product-gallery/30th-celebration-battle-deck-espeon-ex-and-30th-celebration-battle-deck-umbreon-ex"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"))
    page.goto(URL, timeout=30000, wait_until="networkidle")
    html = page.content()
    browser.close()

print("LEN:", len(html))
m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
print("OG_IMAGE:", m.group(1) if m else None)
for m2 in re.finditer(r'incrementals/2026/([a-z0-9\-]+)/', html):
    print("SLUG_SEEN:", m2.group(1))
ld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
for block in ld:
    try:
        data = json.loads(block)
    except Exception:
        continue
    print("JSONLD:", json.dumps(data)[:2000])
