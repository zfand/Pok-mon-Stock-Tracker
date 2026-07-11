"""Pure parsing helpers for the pokemon.com product-gallery scraper.

Kept free of network calls so they're unit-testable against fixture
HTML/XML strings — see tests/test_gallery_parse.py.
"""

import datetime
import json
import re

MONTH_DATE_RE = re.compile(
    r'(January|February|March|April|May|June|July|August|September|October|'
    r'November|December)\s+(\d{1,2}),?\s+(\d{4})'
)
RELEASE_KEYWORDS_RE = re.compile(r'(release|available|in stores|on sale)', re.IGNORECASE)

# Deliberately specific, not generic terms like "captcha" or "access
# denied" — those show up incidentally in normal pages' cookie-consent and
# reCAPTCHA boilerplate (confirmed: a real, successfully-rendered 160KB
# product page tripped a looser version of this list on that noise alone).
BLOCK_MARKERS = (
    "administrators have been notified",
    "are you a human",
    "pardon our interruption",
    "request unsuccessful",
)
# A genuine challenge/compliance page has been short every time we've seen
# one; a real product page is not. Require both signals together so
# boilerplate mentioning one of the phrases deep in a large real page can't
# misclassify it.
BLOCKED_PAGE_MAX_LEN = 20_000

# Longest/most specific patterns first, so e.g. the Ultra-Premium
# Collection's "-ultra-premium-collections-day-night" suffix strips as a
# whole rather than a shorter, more generic pattern partially matching.
PRODUCT_SUFFIX_PATTERNS = [
    r'-ultra-premium-collections?(-[a-z0-9-]+)?$',
    r'-premium-figure-collection$',
    r'-collectors?-chest$',
    r'-deluxe-pin-collection$',
    r'-pin-collection$',
    r'-mini-tins?$',
    r'-poster-collection$',
    r'-booster-bundle$',
    r'-elite-trainer-box$',
]


def looks_blocked(html: str) -> bool:
    if len(html) >= BLOCKED_PAGE_MAX_LEN:
        return False
    snippet = html.lower()
    return any(m in snippet for m in BLOCK_MARKERS)


def derive_set_slug(product_slug: str) -> tuple[str, bool]:
    """Best-effort split of a product slug into its parent set slug.

    Returns (set_slug, guessed). guessed=True means no known product-type
    suffix matched, so the whole slug was used as a fallback "set" name —
    treat these as low confidence until reviewed by a human.
    """
    for pattern in PRODUCT_SUFFIX_PATTERNS:
        stripped = re.sub(pattern, '', product_slug, flags=re.IGNORECASE)
        if stripped != product_slug and stripped:
            return stripped, False
    return product_slug, True


def extract_jsonld_products(html: str) -> list[dict]:
    """All dicts from <script type="application/ld+json"> blocks whose
    @type mentions "Product"."""
    out = []
    for m in re.finditer(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(m.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            t = node.get('@type', '')
            types = t if isinstance(t, list) else [t]
            if any('product' in str(x).lower() for x in types):
                out.append(node)
    return out


def _iso_date(month_name: str, day: str, year: str) -> str | None:
    try:
        month = datetime.datetime.strptime(month_name, '%B').month
        return datetime.date(int(year), month, int(day)).isoformat()
    except ValueError:
        return None


def extract_release_date(html: str, jsonld_products: list[dict]) -> tuple[str | None, str | None]:
    """Returns (iso_date_or_None, raw_text_or_None). Prefers structured
    JSON-LD fields; falls back to a "release"-adjacent date in page text,
    then any month-name date at all."""
    for node in jsonld_products:
        for key in ('releaseDate', 'datePublished', 'productionDate'):
            raw = node.get(key)
            if not raw:
                continue
            raw = str(raw)
            m = re.match(r'(\d{4})-(\d{2})-(\d{2})', raw)
            if m:
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", raw
            m2 = MONTH_DATE_RE.search(raw)
            if m2:
                return _iso_date(*m2.groups()), m2.group(0)

    best = None
    for m in MONTH_DATE_RE.finditer(html):
        window = html[max(0, m.start() - 60): m.start()]
        if RELEASE_KEYWORDS_RE.search(window):
            best = m
            break
    if best is None:
        best = MONTH_DATE_RE.search(html)
    if best:
        return _iso_date(*best.groups()), best.group(0)
    return None, None


def extract_name(html: str, jsonld_products: list[dict]) -> str | None:
    for node in jsonld_products:
        if node.get('name'):
            return str(node['name'])
    m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'<title>([^<]+)</title>', html)
    if m:
        return m.group(1).split('|')[0].strip()
    return None


def extract_image(html: str, jsonld_products: list[dict]) -> str | None:
    for node in jsonld_products:
        img = node.get('image')
        if isinstance(img, list) and img:
            return str(img[0])
        if isinstance(img, str) and img:
            return img
    m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(
        r'src="(https://www\.pokemon\.com/static-assets/[^"]+\.(?:png|jpg|jpeg))"', html)
    if m:
        return m.group(1)
    return None


def parse_sitemap_locs(xml_text: str) -> list[str]:
    return re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', xml_text)


def is_sitemap_index(xml_text: str) -> bool:
    return '<sitemapindex' in xml_text[:2000]
