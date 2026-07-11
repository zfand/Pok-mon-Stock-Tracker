import copy

import pytest


BASE_CFG = {
    "set": {
        "name": "Pokémon TCG 30th Anniversary Celebrations",
        "search_query": "pokemon tcg 30th anniversary",
        "exclude": [],
    },
    "products": [
        {
            "id": "elite-trainer-box",
            "name": "Elite Trainer Box",
            "alert": True,
            "purchase": False,
            "max_price_usd": 80,
            "must_include": [["30th"], ["elite trainer box", "etb"]],
            "exclude": ["sleeve", "playmat", "binder"],
            "image": "",
            "watch_urls": {},
        },
        {
            "id": "booster-bundle",
            "name": "Booster Bundle",
            "alert": False,
            "purchase": False,
            "must_include": [["30th"], ["booster bundle"]],
            "image": "",
            "watch_urls": {},
        },
    ],
    "retailers": {
        "target": {"enabled": True},
        "walmart": {"enabled": True},
        "bestbuy": {"enabled": True},
        "gamestop": {"enabled": True},
        "pokemoncenter": {"enabled": True},
        "amazon": {"enabled": True},
    },
    "notifications": {
        "ntfy_topic": "test-topic",
        "ntfy_server": "https://ntfy.sh",
        "notify_on_persistent_block": True,
    },
    "auto_checkout": {
        "enabled": False,
        "max_price_usd": 80,
        "quantity": 1,
        "retailers": ["pokemoncenter", "target"],
    },
}


@pytest.fixture
def cfg():
    return copy.deepcopy(BASE_CFG)


class FakeResponse:
    def __init__(self, *, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Routes session.get(url) to a canned response by URL substring."""

    def __init__(self, routes):
        # routes: list of (url_substring, FakeResponse)
        self.routes = routes
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        for substr, resp in self.routes:
            if substr in url:
                return resp
        raise AssertionError(f"no fake route for {url}")
