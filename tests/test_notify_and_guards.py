"""ntfy payload construction + auto-checkout guardrails."""

import tracker.notify as notify_mod
from tracker.checkout import runner
from tracker.models import Hit


class _Sent:
    def __init__(self):
        self.calls = []

    def __call__(self, url, data=None, headers=None, timeout=None):
        self.calls.append({"url": url, "data": data, "headers": headers})

        class R:
            @staticmethod
            def raise_for_status():
                pass
        return R()


def test_notify_stock_is_urgent_with_click_url(cfg, monkeypatch):
    sent = _Sent()
    monkeypatch.setattr(notify_mod.requests, "post", sent)
    hit = Hit("Target", "Pokemon 30th ETB", "https://t.example/p/1",
              in_stock=True, price="$59.99")
    notify_mod.notify_stock(cfg, hit)
    (call,) = sent.calls
    assert call["url"] == "https://ntfy.sh/test-topic"
    assert call["headers"]["Priority"] == "urgent"
    assert call["headers"]["Click"] == hit.url
    assert b"IN STOCK at Target" in call["headers"]["Title"]
    assert hit.url.encode() in call["data"]


def test_notify_new_listing_not_buyable_wording(cfg, monkeypatch):
    sent = _Sent()
    monkeypatch.setattr(notify_mod.requests, "post", sent)
    hit = Hit("Target", "Pokemon 30th Figure Collection", "https://t.example/p/3",
              in_stock=False, status="OUT_OF_STOCK")
    notify_mod.notify_new_listing(cfg, hit)
    (call,) = sent.calls
    assert b"not buyable yet" in call["headers"]["Title"]
    assert call["headers"]["Priority"] == "high"


def test_notify_new_listing_already_buyable_wording(cfg, monkeypatch):
    sent = _Sent()
    monkeypatch.setattr(notify_mod.requests, "post", sent)
    hit = Hit("Target", "Pokemon 30th Figure Collection", "https://t.example/p/3",
              in_stock=True, price="$49.99", status="IN_STOCK")
    notify_mod.notify_new_listing(cfg, hit)
    (call,) = sent.calls
    title = call["headers"]["Title"]
    assert b"already buyable" in title
    assert b"$49.99" in title
    assert b"not buyable" not in title


def test_notify_uses_env_topic_override(cfg, monkeypatch):
    # config.load_config maps NTFY_TOPIC env into cfg; simulate the result
    cfg["notifications"]["ntfy_topic"] = "secret-topic"
    sent = _Sent()
    monkeypatch.setattr(notify_mod.requests, "post", sent)
    notify_mod.notify_info(cfg, "t", "b")
    assert sent.calls[0]["url"].endswith("/secret-topic")


def test_notify_without_topic_skips_without_http_call(cfg, monkeypatch, capsys):
    cfg["notifications"]["ntfy_topic"] = ""
    monkeypatch.setattr(notify_mod.requests, "post",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no HTTP call")))
    notify_mod.notify_info(cfg, "some title", "body")  # must not raise
    assert "SKIPPED" in capsys.readouterr().out


def test_notify_failure_never_leaks_topic_or_url(cfg, monkeypatch, capsys):
    # Public-repo requirement: connection errors embed the topic-bearing URL
    # in their message; that must never reach stdout (public Actions logs).
    cfg["notifications"]["ntfy_topic"] = "sekrit-topic"

    def fail(url, **kwargs):
        raise notify_mod.requests.exceptions.ConnectionError(
            f"Max retries exceeded with url: {url}")

    monkeypatch.setattr(notify_mod.requests, "post", fail)
    hit = Hit("Target", "Pokemon 30th ETB", "https://t/p", in_stock=True)
    notify_mod.notify_stock(cfg, hit)  # must not raise either
    out = capsys.readouterr().out
    assert "sekrit-topic" not in out
    assert "ntfy.sh" not in out
    assert "FAILED" in out


# --- auto-checkout guardrails -------------------------------------------------

def _hit(price="$59.99", retailer="Target"):
    return Hit(retailer, "Pokemon 30th ETB", "https://x/p", in_stock=True,
               price=price, product_id="elite-trainer-box")


def _etb(cfg, **overrides):
    product = dict(cfg["products"][0])
    product.update(overrides)
    return product


def test_price_cap_prefers_product_over_global(cfg):
    assert runner._price_ok(cfg, _hit("$59.99"), _etb(cfg))
    assert not runner._price_ok(cfg, _hit("$99.99"), _etb(cfg))          # product cap 80
    assert runner._price_ok(cfg, _hit("$99.99"), _etb(cfg, max_price_usd=120))
    assert runner._price_ok(cfg, _hit(""), _etb(cfg))  # unknown price: allowed


def test_checkout_skipped_when_purchase_flag_off(cfg, monkeypatch):
    monkeypatch.setenv("TARGET_EMAIL", "e")
    monkeypatch.setenv("TARGET_PASSWORD", "p")
    monkeypatch.setattr(runner, "notify_info",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no notify")))
    runner.run_checkout(cfg, _hit(), _etb(cfg, purchase=False))  # must not raise


def test_checkout_skipped_without_credentials(cfg, monkeypatch):
    monkeypatch.delenv("TARGET_EMAIL", raising=False)
    monkeypatch.delenv("TARGET_PASSWORD", raising=False)
    monkeypatch.setattr(runner, "notify_info",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no notify")))
    runner.run_checkout(cfg, _hit(), _etb(cfg, purchase=True))


def test_checkout_skipped_for_unconfigured_retailer(cfg, monkeypatch):
    monkeypatch.setenv("TARGET_EMAIL", "e")
    monkeypatch.setenv("TARGET_PASSWORD", "p")
    cfg["auto_checkout"]["retailers"] = ["pokemoncenter"]  # Target not enabled
    monkeypatch.setattr(runner, "notify_info",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no notify")))
    runner.run_checkout(cfg, _hit(), _etb(cfg, purchase=True))


def test_checkout_over_price_cap_notifies_and_skips(cfg, monkeypatch):
    monkeypatch.setenv("TARGET_EMAIL", "e")
    monkeypatch.setenv("TARGET_PASSWORD", "p")
    infos = []
    monkeypatch.setattr(runner, "notify_info", lambda c, t, b: infos.append(t))
    runner.run_checkout(cfg, _hit("$199.99"), _etb(cfg, purchase=True))
    assert infos and "Skipped" in infos[0]
