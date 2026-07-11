"""Pokémon Center checkout flow (Playwright).

Selectors are best-guess until a real listing exists to test against —
expect to tune them on the first live run. The flow assumes shipping and
payment are already saved on the account.
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
            page.goto("https://www.pokemoncenter.com/login", timeout=TIMEOUT)
            page.fill('input[type="email"]', email)
            page.fill('input[type="password"]', password)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=TIMEOUT)

            # Product page → add to cart
            page.goto(hit.url, timeout=TIMEOUT)
            add_btn = page.locator(
                'button:has-text("Add to Cart"), button:has-text("Pre-Order")').first
            add_btn.click(timeout=TIMEOUT)
            for _ in range(quantity - 1):
                add_btn.click(timeout=TIMEOUT)

            # Checkout
            page.goto("https://www.pokemoncenter.com/cart", timeout=TIMEOUT)
            page.click('button:has-text("Checkout")', timeout=TIMEOUT)
            page.wait_for_load_state("networkidle", timeout=TIMEOUT)

            if not confirm:
                return ("DRY RUN — item is in your cart at the review step. "
                        "Finish the purchase in your browser, or set "
                        "CONFIRM_PURCHASE=true for future runs.")

            page.click('button:has-text("Place Order")', timeout=TIMEOUT)
            page.wait_for_load_state("networkidle", timeout=TIMEOUT)
            return "ORDER PLACED — check your email for confirmation."
        finally:
            browser.close()
