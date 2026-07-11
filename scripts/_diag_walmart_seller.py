"""One-off diagnostic: what field in Walmart's __NEXT_DATA__ item payload
identifies "Sold and shipped by Walmart.com" vs a third-party marketplace
seller? Uses a live, currently-stocked Pokemon TCG query (not the 30th
Celebration set, which has zero listings yet) so there's real seller
variety to inspect. Delete this file (and its temp workflow) once answered.
"""
import json
import re
import sys

import requests

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', re.DOTALL)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def main() -> int:
    r = requests.get(
        "https://www.walmart.com/search",
        params={"q": "pokemon tcg elite trainer box"},
        headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
        timeout=25,
    )
    print(f"status={r.status_code} len={len(r.text)}")
    m = NEXT_DATA_RE.search(r.text)
    if not m:
        print("no __NEXT_DATA__ found")
        print(r.text[:500])
        return 0
    data = json.loads(m.group(1))
    stacks = (data.get("props", {}).get("pageProps", {})
              .get("initialData", {}).get("searchResult", {}).get("itemStacks", []))
    items = [it for stack in stacks for it in (stack.get("items") or [])]
    print(f"{len(items)} item(s) found\n")

    # Dump full JSON for the first few items so any seller-ish key is visible.
    seller_like_keys = set()
    for item in items[:20]:
        for k in item.keys():
            if "seller" in k.lower() or "fulfilledby" in k.lower() or "sold" in k.lower() or "1p" in k.lower() or "marketplace" in k.lower():
                seller_like_keys.add(k)
    print("seller-ish top-level keys seen across first 20 items:", seller_like_keys)

    for i, item in enumerate(items[:5]):
        print(f"\n--- item {i}: {item.get('name')!r} ---")
        for k in sorted(item.keys()):
            if k in seller_like_keys or k in ("sellerId", "sellerName", "sellerDisplayName"):
                print(f"  {k}: {item[k]!r}")
        # also dump the whole thing compactly for the first item only
        if i == 0:
            print("  FULL JSON:", json.dumps(item, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
