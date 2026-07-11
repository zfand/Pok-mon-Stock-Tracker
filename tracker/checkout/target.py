"""Target checkout flow (Playwright).

Selectors are best-guess until a real listing exists to test against —
expect to tune them on the first live run. The flow assumes shipping and
payment are already saved on the account (Target re-prompts for the card
CVV on some checkouts; if it does, the run stops and notifies you).
"""

from playwright.sync_api import sync_playwright

from ..models import Hit

TIMEOUT = 30_000


def checkout(hit: Hit, email: str, password: str, *, confirm: bool,
             quantity: int = 1) -> str:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        try:
            # Log in
            page.goto("https://www.target.com/account", timeout=TIMEOUT)
            page.fill("#username", email)
            page.click('button:has-text("Continue")')
            page.fill("#password", password)
            page.click('button:has-text("Sign in")')
            page.wait_for_load_state("networkidle", timeout=TIMEOUT)

            # Product page → shipping fulfillment → add to cart
            page.goto(hit.url, timeout=TIMEOUT)
            ship = page.locator('button[data-test="fulfillment-cell-shipping"]')
            if ship.count():
                ship.first.click()
            page.click('button:has-text("Add to cart"), button:has-text("Preorder")',
                       timeout=TIMEOUT)
            decline = page.locator('button:has-text("Decline coverage")')
            if decline.count():
                decline.first.click()

            # Checkout
            page.goto("https://www.target.com/cart", timeout=TIMEOUT)
            page.click('button[data-test="checkout-button"]', timeout=TIMEOUT)
            page.wait_for_load_state("networkidle", timeout=TIMEOUT)

            if page.locator('input[name="cvv"]').count():
                return ("STOPPED — Target is asking for your card CVV, which "
                        "this flow never types. Finish manually: " + hit.url)

            if not confirm:
                return ("DRY RUN — item is in your cart at the review step. "
                        "Finish the purchase in your browser, or set "
                        "CONFIRM_PURCHASE=true for future runs.")

            page.click('button:has-text("Place your order")', timeout=TIMEOUT)
            page.wait_for_load_state("networkidle", timeout=TIMEOUT)
            return "ORDER PLACED — check your email for confirmation."
        finally:
            browser.close()
