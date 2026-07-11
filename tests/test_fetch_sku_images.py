from scripts.fetch_sku_images import derive_variants


def test_strips_celebration():
    assert derive_variants("30th-celebration-poster-collection") == \
        ["30th-poster-collection"]


def test_strips_and():
    assert derive_variants(
        "30th-celebration-sylveon-ex-box-and-greninja-ex-box") == [
        "30th-sylveon-ex-box-and-greninja-ex-box",
        "30th-celebration-sylveon-ex-box-greninja-ex-box",
    ]


def test_slug_with_no_known_pattern_has_no_variants():
    assert derive_variants("figure-collection") == []


def test_never_returns_the_original_slug():
    assert "30th-celebration-poster-collection" not in \
        derive_variants("30th-celebration-poster-collection")
