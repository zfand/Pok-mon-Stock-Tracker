import json

from scripts.gallery_parse import (
    derive_set_slug, extract_image, extract_jsonld_products, extract_name,
    extract_release_date, is_sitemap_index, looks_blocked, parse_sitemap_locs,
)


# --- derive_set_slug ---------------------------------------------------------

def test_strips_known_product_suffix():
    assert derive_set_slug("30th-celebration-elite-trainer-box") == ("30th-celebration", False)


def test_strips_ultra_premium_with_variant_suffix():
    assert derive_set_slug("30th-celebration-ultra-premium-collections-day-night") == \
        ("30th-celebration", False)


def test_strips_plain_ultra_premium_no_variant():
    assert derive_set_slug("some-set-ultra-premium-collection") == ("some-set", False)


def test_strips_collectors_chest_apostrophe_variant():
    assert derive_set_slug("some-set-collectors-chest") == ("some-set", False)


def test_unrecognized_suffix_falls_back_to_whole_slug_guessed():
    set_slug, guessed = derive_set_slug("some-totally-novel-product-type")
    assert set_slug == "some-totally-novel-product-type"
    assert guessed is True


# --- extract_jsonld_products --------------------------------------------------

def test_extracts_single_product_jsonld():
    html = ('<script type="application/ld+json">'
            + json.dumps({"@type": "Product", "name": "Elite Trainer Box"})
            + "</script>")
    products = extract_jsonld_products(html)
    assert len(products) == 1
    assert products[0]["name"] == "Elite Trainer Box"


def test_extracts_from_list_and_ignores_non_product():
    html = ('<script type="application/ld+json">'
            + json.dumps([{"@type": "BreadcrumbList"}, {"@type": "Product", "name": "X"}])
            + "</script>")
    products = extract_jsonld_products(html)
    assert len(products) == 1 and products[0]["name"] == "X"


def test_malformed_jsonld_is_skipped_not_fatal():
    html = '<script type="application/ld+json">{not valid json</script>'
    assert extract_jsonld_products(html) == []


# --- extract_release_date -----------------------------------------------------

def test_release_date_from_jsonld_iso():
    products = [{"releaseDate": "2026-09-16"}]
    iso, raw = extract_release_date("<html></html>", products)
    assert iso == "2026-09-16"


def test_release_date_from_jsonld_month_name():
    products = [{"releaseDate": "September 16, 2026"}]
    iso, raw = extract_release_date("<html></html>", products)
    assert iso == "2026-09-16"
    assert raw == "September 16, 2026"


def test_release_date_from_page_text_near_keyword():
    html = "<p>Some filler text. Available in stores September 16, 2026 nationwide.</p>"
    iso, raw = extract_release_date(html, [])
    assert iso == "2026-09-16"


def test_release_date_falls_back_to_any_date_when_no_keyword_nearby():
    html = "<p>Copyright July 4, 2020 The Pokémon Company.</p>"
    iso, raw = extract_release_date(html, [])
    assert iso == "2020-07-04"


def test_release_date_none_when_absent():
    assert extract_release_date("<p>no dates here</p>", []) == (None, None)


# --- extract_name / extract_image --------------------------------------------

def test_extract_name_prefers_jsonld():
    assert extract_name('<meta property="og:title" content="Wrong">',
                         [{"name": "Right"}]) == "Right"


def test_extract_name_falls_back_to_og_title():
    assert extract_name('<meta property="og:title" content="From OG">', []) == "From OG"


def test_extract_name_falls_back_to_title_tag_stripping_site_suffix():
    assert extract_name('<title>Elite Trainer Box | Pokemon.com</title>', []) == "Elite Trainer Box"


def test_extract_image_prefers_jsonld_list():
    assert extract_image("", [{"image": ["https://a/1.png", "https://a/2.png"]}]) == "https://a/1.png"


def test_extract_image_falls_back_to_og_image():
    html = '<meta property="og:image" content="https://www.pokemon.com/x.png">'
    assert extract_image(html, []) == "https://www.pokemon.com/x.png"


def test_extract_image_falls_back_to_asset_cdn_src():
    html = '<img src="https://www.pokemon.com/static-assets/foo/bar-169-en.png">'
    assert extract_image(html, []) == "https://www.pokemon.com/static-assets/foo/bar-169-en.png"


# --- looks_blocked -------------------------------------------------------------

def test_looks_blocked_true_for_challenge_page():
    assert looks_blocked("... administrators have been notified and will review ...")


def test_looks_blocked_false_for_normal_page():
    assert not looks_blocked("<html>Elite Trainer Box product details</html>")


def test_looks_blocked_false_for_large_real_page_with_incidental_boilerplate():
    # Regression: a real, fully-rendered 160KB product page tripped the
    # detector purely because its cookie-consent/reCAPTCHA scripts happen
    # to mention "captcha" — length must gate the marker check.
    html = ("<html>reCAPTCHA widget script mentions captcha handling here. "
            + "Elite Trainer Box $59.99. " * 2000 + "</html>")
    assert len(html) > 20_000
    assert not looks_blocked(html)


def test_looks_blocked_true_for_short_genuine_challenge_page():
    assert looks_blocked("Pardon our interruption while we verify you're not a robot.")


# --- sitemap helpers -----------------------------------------------------------

def test_parse_sitemap_locs():
    xml = ("<urlset><url><loc>https://a/1</loc></url>"
           "<url><loc>https://a/2</loc></url></urlset>")
    assert parse_sitemap_locs(xml) == ["https://a/1", "https://a/2"]


def test_is_sitemap_index_true():
    assert is_sitemap_index("<sitemapindex><sitemap><loc>x</loc></sitemap></sitemapindex>")


def test_is_sitemap_index_false_for_urlset():
    assert not is_sitemap_index("<urlset><url><loc>x</loc></url></urlset>")
