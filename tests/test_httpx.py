from tests.conftest import FakeResponse
from tracker.httpx import looks_blocked


def test_403_is_blocked():
    assert looks_blocked(FakeResponse(status_code=403, text="ok-looking body"))


def test_captcha_body_is_blocked():
    assert looks_blocked(FakeResponse(text="<html>please solve this CAPTCHA</html>"))


def test_normal_page_not_blocked():
    assert not looks_blocked(FakeResponse(text="<html>Elite Trainer Box $59.99</html>"))
