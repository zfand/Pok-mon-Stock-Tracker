from tracker.config import match_product, watch_urls_for


def _pid(cfg, title):
    p = match_product(cfg, title)
    return p["id"] if p else None


def test_matches_official_style_etb_title(cfg):
    assert _pid(cfg, "Pokémon TCG: 30th Anniversary Celebrations Elite Trainer Box") \
        == "elite-trainer-box"


def test_matches_abbreviated_etb(cfg):
    assert _pid(cfg, "Pokemon 30th Celebrations ETB") == "elite-trainer-box"


def test_case_insensitive(cfg):
    assert _pid(cfg, "POKEMON 30TH ANNIVERSARY ELITE TRAINER BOX") == "elite-trainer-box"


def test_classifies_other_products_in_set(cfg):
    assert _pid(cfg, "Pokemon TCG 30th Anniversary Booster Bundle") == "booster-bundle"


def test_rejects_25th_celebrations(cfg):
    # The 25th-anniversary product from 2021 must not match
    assert _pid(cfg, "Pokemon TCG: Celebrations Elite Trainer Box") is None


def test_product_exclude_words(cfg):
    assert _pid(cfg, "Pokemon 30th Anniversary ETB Card Sleeves 65ct") is None
    assert _pid(cfg, "Pokemon 30th Elite Trainer Box Playmat") is None


def test_set_level_exclude_rejects_everything(cfg):
    cfg["set"]["exclude"] = ["japanese"]
    assert _pid(cfg, "Pokemon 30th Elite Trainer Box (Japanese)") is None


def test_unknown_product_type_matches_nothing(cfg):
    assert _pid(cfg, "Pokemon 30th Anniversary Lunchbox") is None


def test_watch_urls_for_collects_per_retailer(cfg):
    cfg["products"][0]["watch_urls"] = {"target": ["https://t/1"], "amazon": ["https://a/1"]}
    cfg["products"][1]["watch_urls"] = {"target": ["https://t/2"]}
    urls = watch_urls_for(cfg, "target")
    assert [(u, p["id"]) for u, p in urls] == \
        [("https://t/1", "elite-trainer-box"), ("https://t/2", "booster-bundle")]
    assert watch_urls_for(cfg, "gamestop") == []
