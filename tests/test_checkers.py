"""Retailer parsers against canned fixture responses (no network)."""

import json

from tests.conftest import FakeResponse, FakeSession
from tracker.checkers import amazon, bestbuy, gamestop, pokemoncenter, target, walmart


# --- Target -----------------------------------------------------------------

TARGET_SEARCH = {
    "data": {"search": {"products": [
        {
            "tcin": "111",
            "item": {
                "product_description": {"title": "Pokémon TCG: 30th Anniversary Elite Trainer Box"},
                "enrichment": {"buy_url": "https://www.target.com/p/-/A-111"},
            },
            "price": {"formatted_current_price": "$59.99"},
        },
        {
            "tcin": "222",
            "item": {
                "product_description": {"title": "Pokemon TCG 30th Anniversary Booster Bundle"},
                "enrichment": {},
            },
        },
        {
            "tcin": "333",
            "item": {"product_description": {"title": "Pokemon plush"}, "enrichment": {}},
        },
    ]}},
}

TARGET_FULFILLMENT = {
    "data": {"product_summaries": [
        {"tcin": "111",
         "fulfillment": {"shipping_options": {"availability_status": "PRE_ORDER_SELLABLE"}}},
        {"tcin": "222",
         "fulfillment": {"shipping_options": {"availability_status": "OUT_OF_STOCK"}}},
    ]},
}


def test_target_classifies_multiple_products(cfg):
    session = FakeSession([
        ("plp_search_v2", FakeResponse(json_data=TARGET_SEARCH)),
        ("product_summary_with_fulfillment", FakeResponse(json_data=TARGET_FULFILLMENT)),
    ])
    result = target.check(session, cfg)
    assert not result.error
    by_id = {h.product_id: h for h in result.hits}
    assert set(by_id) == {"elite-trainer-box", "booster-bundle"}  # plush filtered
    assert by_id["elite-trainer-box"].in_stock
    assert by_id["elite-trainer-box"].price == "$59.99"
    assert not by_id["booster-bundle"].in_stock


def test_target_watch_url_tcin_extraction(cfg):
    cfg["products"][0]["watch_urls"] = {"target": ["https://www.target.com/p/-/A-444"]}
    session = FakeSession([
        ("plp_search_v2", FakeResponse(json_data={"data": {"search": {"products": []}}})),
        ("product_summary_with_fulfillment", FakeResponse(json_data={"data": {"product_summaries": [
            {"tcin": "444", "fulfillment": {"shipping_options": {"availability_status": "OUT_OF_STOCK"}}},
        ]}})),
    ])
    result = target.check(session, cfg)
    assert len(result.hits) == 1
    assert result.hits[0].product_id == "elite-trainer-box"
    assert not result.hits[0].in_stock


# --- Walmart ----------------------------------------------------------------

def _walmart_html(items):
    data = {"props": {"pageProps": {"initialData": {"searchResult": {
        "itemStacks": [{"items": items}]}}}}}
    return ('<html><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(data) + "</script></html>")


def test_walmart_parses_buyable_item(cfg):
    html = _walmart_html([
        {"name": "Pokemon TCG 30th Anniversary ETB", "canonicalUrl": "/ip/123",
         "canAddToCart": True, "availabilityStatusV2": {"value": "IN_STOCK"},
         "priceInfo": {"linePrice": "$59.99"}},
        {"name": "Pokemon plush", "canonicalUrl": "/ip/999", "canAddToCart": True},
    ])
    session = FakeSession([("walmart.com/search", FakeResponse(text=html))])
    result = walmart.check(session, cfg)
    assert len(result.hits) == 1
    hit = result.hits[0]
    assert hit.in_stock
    assert hit.product_id == "elite-trainer-box"
    assert hit.url == "https://www.walmart.com/ip/123"
    assert hit.price == "$59.99"


def test_walmart_explicit_first_party_seller_is_buyable(cfg):
    html = _walmart_html([
        {"name": "Pokemon TCG 30th Anniversary ETB", "canonicalUrl": "/ip/123",
         "canAddToCart": True, "availabilityStatusV2": {"value": "IN_STOCK"},
         "priceInfo": {"linePrice": "$59.99"}, "sellerName": "Walmart.com"},
    ])
    session = FakeSession([("walmart.com/search", FakeResponse(text=html))])
    result = walmart.check(session, cfg)
    assert result.hits[0].in_stock


def test_walmart_third_party_seller_never_reported_buyable(cfg):
    # This is the actual scalper-markup scenario: Walmart's own API says
    # in stock / add-to-cart eligible, but a marketplace seller (not
    # Walmart) is fulfilling it — must never trigger a "buy now" push.
    html = _walmart_html([
        {"name": "Pokemon TCG 30th Anniversary ETB", "canonicalUrl": "/ip/123",
         "canAddToCart": True, "availabilityStatusV2": {"value": "IN_STOCK"},
         "priceInfo": {"linePrice": "$149.99"}, "sellerName": "ACME Collectibles LLC"},
    ])
    session = FakeSession([("walmart.com/search", FakeResponse(text=html))])
    result = walmart.check(session, cfg)
    assert len(result.hits) == 1
    hit = result.hits[0]
    assert not hit.in_stock
    assert hit.status == "THIRD_PARTY_SELLER:ACME Collectibles LLC"


def test_walmart_bot_block_sets_flag(cfg):
    session = FakeSession([
        ("walmart.com/search", FakeResponse(text="Robot or human? Verify")),
    ])
    result = walmart.check(session, cfg)
    assert result.blocked
    assert result.hits == []


# --- Best Buy ---------------------------------------------------------------

def test_bestbuy_official_api(cfg):
    cfg["retailers"]["bestbuy"]["api_key"] = "k"
    session = FakeSession([("api.bestbuy.com", FakeResponse(json_data={"products": [
        {"name": "Pokemon 30th Anniversary Elite Trainer Box", "sku": 1,
         "salePrice": 59.99, "onlineAvailability": True, "url": "https://bby/1"},
        {"name": "Pokemon 30th sleeve", "sku": 2, "onlineAvailability": True, "url": "u"},
    ]}))])
    result = bestbuy.check(session, cfg)
    assert len(result.hits) == 1
    assert result.hits[0].in_stock
    assert result.hits[0].product_id == "elite-trainer-box"
    assert result.hits[0].price == "$59.99"


def test_bestbuy_scrape_button_state(cfg):
    html = '''
    <div><h4 class="sku-title"><a href="/site/pokemon-30th-etb/6501.p">Pokemon TCG 30th Anniversary Elite Trainer Box</a></h4></div>
    <button data-button-state="SOLD_OUT" data-sku-id="6501">Sold Out</button>
    '''
    session = FakeSession([("searchpage.jsp", FakeResponse(text=html))])
    result = bestbuy.check(session, cfg)
    assert len(result.hits) == 1
    assert not result.hits[0].in_stock
    assert result.hits[0].status == "SOLD_OUT"


def test_bestbuy_watch_url_product_page(cfg):
    cfg["products"][0]["watch_urls"] = {"bestbuy": ["https://www.bestbuy.com/site/x/650.p"]}
    session = FakeSession([
        ("searchpage.jsp", FakeResponse(text="<html></html>")),
        ("/site/x/650.p", FakeResponse(text='<button data-button-state="PRE_ORDER">')),
    ])
    result = bestbuy.check(session, cfg)
    assert len(result.hits) == 1
    assert result.hits[0].in_stock
    assert result.hits[0].product_id == "elite-trainer-box"


# --- GameStop ---------------------------------------------------------------

def test_gamestop_jsonld_preorder(cfg):
    cfg["products"][0]["watch_urls"] = {"gamestop": ["https://www.gamestop.com/products/x.html"]}
    page = ('<script type="application/ld+json">'
            + json.dumps({"@type": "Product",
                          "offers": {"availability": "https://schema.org/PreOrder"}})
            + "</script>")
    session = FakeSession([
        ("gamestop.com/search", FakeResponse(text="<html></html>")),
        ("products/x.html", FakeResponse(text=page)),
    ])
    result = gamestop.check(session, cfg)
    assert len(result.hits) == 1
    assert result.hits[0].in_stock
    assert result.hits[0].status == "PREORDER"
    assert result.hits[0].product_id == "elite-trainer-box"


# --- Pokémon Center ----------------------------------------------------------

def test_pokemoncenter_blocked_is_flagged_not_fatal(cfg):
    session = FakeSession([
        ("pokemoncenter.com/search", FakeResponse(status_code=403, text="Access Denied")),
    ])
    result = pokemoncenter.check(session, cfg)
    assert result.blocked
    assert result.hits == []


def test_pokemoncenter_watch_url_in_stock(cfg):
    cfg["products"][0]["watch_urls"] = {"pokemoncenter": ["https://www.pokemoncenter.com/product/p1"]}
    session = FakeSession([
        ("pokemoncenter.com/search", FakeResponse(text="<html></html>")),
        ("/product/p1", FakeResponse(text='{"availability":"https://schema.org/InStock"}')),
    ])
    result = pokemoncenter.check(session, cfg)
    assert len(result.hits) == 1
    assert result.hits[0].in_stock
    assert result.hits[0].product_id == "elite-trainer-box"


# --- Amazon -------------------------------------------------------------------

def test_amazon_buyable_page(cfg):
    cfg["products"][0]["watch_urls"] = {"amazon": ["https://www.amazon.com/dp/B0TEST"]}
    html = ('<span id="productTitle"> Pokemon 30th ETB </span>'
            '<div id="add-to-cart-button"></div>')
    session = FakeSession([("/dp/B0TEST", FakeResponse(text=html))])
    result = amazon.check(session, cfg)
    assert len(result.hits) == 1
    assert result.hits[0].in_stock
    assert result.hits[0].title == "Pokemon 30th ETB"
    assert result.hits[0].product_id == "elite-trainer-box"


def test_amazon_unavailable_page(cfg):
    cfg["products"][0]["watch_urls"] = {"amazon": ["https://www.amazon.com/dp/B0TEST"]}
    session = FakeSession([
        ("/dp/B0TEST", FakeResponse(text="<p>Currently unavailable</p>")),
    ])
    result = amazon.check(session, cfg)
    assert len(result.hits) == 1
    assert not result.hits[0].in_stock


def test_amazon_no_watch_urls_no_requests(cfg):
    session = FakeSession([])
    result = amazon.check(session, cfg)
    assert result.hits == [] and not session.requests
