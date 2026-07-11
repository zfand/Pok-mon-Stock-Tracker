"""Notification/state-transition logic — the behavior that decides whether
your phone buzzes and what gets handed to auto-checkout."""

import tracker.main as main_mod
from tracker.models import Hit


def _capture_notifiers(monkeypatch):
    calls = {"stock": [], "new": [], "info": []}
    monkeypatch.setattr(main_mod, "notify_stock", lambda cfg, h: calls["stock"].append(h))
    monkeypatch.setattr(main_mod, "notify_new_listing", lambda cfg, h: calls["new"].append(h))
    monkeypatch.setattr(main_mod, "notify_info", lambda cfg, t, b: calls["info"].append(t))
    return calls


def _hit(in_stock, url="https://t.example/p/1", product_id="elite-trainer-box"):
    return Hit("Target", "Pokemon 30th ETB", url, in_stock=in_stock,
               status="X", product_id=product_id)


def _pmap(cfg):
    return {p["id"]: p for p in cfg["products"]}


def test_new_buyable_listing_notifies_stock(cfg, monkeypatch):
    calls = _capture_notifiers(monkeypatch)
    state = {"listings": {}, "blocks": {}}
    hit = _hit(True)
    to_buy = main_mod.process_hits(cfg, state, [hit], _pmap(cfg))
    assert calls["stock"] == [hit]
    assert calls["new"] == []
    assert to_buy == []  # purchase flag is off for the ETB by default
    assert state["listings"][hit.key]["in_stock"] is True
    assert state["listings"][hit.key]["product"] == "elite-trainer-box"


def test_purchase_flagged_product_lands_in_buy_list(cfg, monkeypatch):
    _capture_notifiers(monkeypatch)
    cfg["products"][0]["purchase"] = True
    state = {"listings": {}, "blocks": {}}
    hit = _hit(True)
    to_buy = main_mod.process_hits(cfg, state, [hit], _pmap(cfg))
    assert to_buy == [(hit, cfg["products"][0])]


def test_alert_off_product_first_sighting_gets_new_listing_push_not_urgent(cfg, monkeypatch):
    # Discovery is decoupled from the alert flag: even a product you don't
    # want urgent buy pings for should tell you once when it's first spotted.
    calls = _capture_notifiers(monkeypatch)
    state = {"listings": {}, "blocks": {}}
    hit = _hit(False, url="https://t.example/p/2", product_id="booster-bundle")
    to_buy = main_mod.process_hits(cfg, state, [hit], _pmap(cfg))
    assert calls["stock"] == []
    assert calls["new"] == [hit]
    assert to_buy == []
    assert state["listings"][hit.key]["in_stock"] is False


def test_alert_off_product_first_sighting_already_buyable_still_gets_new_listing_not_urgent(
        cfg, monkeypatch):
    # Already-buyable-on-first-sight for an alert-off product should NOT
    # trigger the urgent "IN STOCK" push (that stays alert-gated) — it
    # should still get exactly the one discovery push.
    calls = _capture_notifiers(monkeypatch)
    state = {"listings": {}, "blocks": {}}
    hit = _hit(True, url="https://t.example/p/2", product_id="booster-bundle")
    to_buy = main_mod.process_hits(cfg, state, [hit], _pmap(cfg))
    assert calls["stock"] == []
    assert calls["new"] == [hit]
    assert to_buy == []
    assert state["listings"][hit.key]["in_stock"] is True  # page still sees it


def test_alert_off_product_subsequent_changes_stay_silent(cfg, monkeypatch):
    # Only the FIRST sighting is a "new listing" — ongoing changes on an
    # alert-off product (e.g. later becoming buyable) still don't push,
    # matching the existing alert-off design for buyability specifically.
    calls = _capture_notifiers(monkeypatch)
    state = {"listings": {}, "blocks": {}}
    url = "https://t.example/p/2"
    main_mod.process_hits(cfg, state, [_hit(False, url=url, product_id="booster-bundle")],
                          _pmap(cfg))
    assert len(calls["new"]) == 1
    main_mod.process_hits(cfg, state, [_hit(True, url=url, product_id="booster-bundle")],
                          _pmap(cfg))
    assert calls["stock"] == []
    assert len(calls["new"]) == 1  # unchanged — no second push


def test_new_unbuyable_listing_notifies_new_listing_only(cfg, monkeypatch):
    calls = _capture_notifiers(monkeypatch)
    state = {"listings": {}, "blocks": {}}
    main_mod.process_hits(cfg, state, [_hit(False)], _pmap(cfg))
    assert calls["stock"] == []
    assert len(calls["new"]) == 1


def test_out_of_stock_to_in_stock_transition_notifies(cfg, monkeypatch):
    calls = _capture_notifiers(monkeypatch)
    state = {"listings": {}, "blocks": {}}
    main_mod.process_hits(cfg, state, [_hit(False)], _pmap(cfg))
    main_mod.process_hits(cfg, state, [_hit(True)], _pmap(cfg))
    assert len(calls["stock"]) == 1


def test_still_in_stock_does_not_renotify(cfg, monkeypatch):
    calls = _capture_notifiers(monkeypatch)
    state = {"listings": {}, "blocks": {}}
    for _ in range(3):
        main_mod.process_hits(cfg, state, [_hit(True)], _pmap(cfg))
    assert len(calls["stock"]) == 1


def test_in_stock_to_out_updates_state_silently_then_renotifies(cfg, monkeypatch):
    calls = _capture_notifiers(monkeypatch)
    state = {"listings": {}, "blocks": {}}
    main_mod.process_hits(cfg, state, [_hit(True)], _pmap(cfg))
    main_mod.process_hits(cfg, state, [_hit(False)], _pmap(cfg))
    assert state["listings"][_hit(False).key]["in_stock"] is False
    main_mod.process_hits(cfg, state, [_hit(True)], _pmap(cfg))
    assert len(calls["stock"]) == 2


def test_block_tracking_notifies_once_per_day_after_24h(cfg, monkeypatch):
    calls = _capture_notifiers(monkeypatch)
    state = {"listings": {}, "blocks": {}}

    t = [1_000_000]
    monkeypatch.setattr(main_mod, "now", lambda: t[0])

    main_mod.track_blocks(cfg, state, "Walmart", blocked=True)
    assert calls["info"] == []  # fresh block: no alarm yet

    t[0] += main_mod.DAY + 60
    main_mod.track_blocks(cfg, state, "Walmart", blocked=True)
    assert len(calls["info"]) == 1  # persistent: one heads-up

    t[0] += 3600
    main_mod.track_blocks(cfg, state, "Walmart", blocked=True)
    assert len(calls["info"]) == 1  # within the same day: no repeat

    main_mod.track_blocks(cfg, state, "Walmart", blocked=False)
    assert "Walmart" not in state["blocks"]  # recovery clears the record
