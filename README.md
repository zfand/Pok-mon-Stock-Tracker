# Pokémon TCG Stock Tracker

Watches retailers for **every product in the Pokémon TCG 30th Anniversary
Celebrations set**, pushes a phone notification the moment an alert-enabled
SKU becomes buyable, and can optionally attempt an automated checkout for
purchase-flagged SKUs.

Runs on a GitHub Actions cron schedule (every ~10 minutes) — no servers, no
cost. A GitHub Pages dashboard shows the whole catalog with per-retailer
status.

## Product catalog

`config.yml` → `products` lists every SKU in the set (the lineup is
provisional until the official product list is announced — edit freely).
Each product has two independent flags:

- `alert: true` — push a notification when it becomes buyable
- `purchase: true` — hand it to auto-checkout as well (requires the global
  `auto_checkout` switches + credential secrets; everything ships off)

Only the Elite Trainer Box has `alert: true` out of the box; all `purchase`
flags are off. Per-product `max_price_usd` caps auto-checkout spend, and
per-product `watch_urls` hold direct listing URLs per retailer.

## Retailers

| Retailer | Method | Reliability |
|---|---|---|
| Target | redsky API (search + fulfillment) | Good |
| Best Buy | Official API with key, page scrape without | Good with key |
| Walmart | Search page JSON | OK, occasional bot blocks |
| GameStop | Search + product page JSON-LD | OK |
| Pokémon Center | Search / product page | Often bot-blocked — expected |
| Amazon | Direct product URLs only | Needs an ASIN in `watch_urls` |

**The single biggest reliability upgrade:** as soon as a listing page exists
anywhere (even out of stock), paste its URL into `watch_urls` in
`config.yml`. Direct page checks beat keyword search everywhere.

## Setup (5 minutes)

1. **Phone push (required)**: the ntfy topic works like a password — anyone
   who knows it can read your alerts *and push fake ones*, so it is
   deliberately **not stored in this repo**. Pick a long random topic name,
   save it as the repo secret `NTFY_TOPIC` (Settings → Secrets and
   variables → Actions), then install the [ntfy](https://ntfy.sh) app
   (iOS/Android) and subscribe to that topic. Without the secret, checks
   still run but notifications are skipped.
2. **Verify**: run the "Check stock" workflow from the Actions tab with the
   *test notification* option ticked — a test push should land on your phone.
3. **Optional, Best Buy**: get a free key at
   [developer.bestbuy.com](https://developer.bestbuy.com) and save it as
   secret `BESTBUY_API_KEY`.
4. Make sure the workflows are on the repo's **default branch** — scheduled
   workflows only fire from there.

The repo contains no secrets (verified against the full git history) and is
designed to be safe as a **public** repository: workflows that hold secrets
only run on schedule/manual dispatch, never for fork PRs, and nothing
topic- or credential-bearing is ever printed to the (world-readable)
Actions logs.

## Notifications you'll get

- 🚨 **IN STOCK / preorder live** (urgent priority) — tap opens the product
  page directly.
- 👀 **New listing spotted** — a matching product page appeared but isn't
  buyable yet. Good moment to add its URL to `watch_urls`.
- ℹ️ A once-a-day note if a retailer has been blocking checks for 24h+.

## Auto-checkout (optional, off by default)

Be aware before enabling: automated purchasing violates most retailers'
terms of service — orders can be cancelled and accounts banned. It is also
fragile: any captcha, queue, or layout change stops the run (this project
deliberately does **not** try to evade bot detection or solve captchas).
The push notification is always the reliable path.

If you still want it:

1. Save shipping + payment on your retailer account ahead of time — the
   flows never type card numbers.
2. Set repo **secrets**: `PC_EMAIL`/`PC_PASSWORD` (Pokémon Center) and/or
   `TARGET_EMAIL`/`TARGET_PASSWORD`.
3. Set `auto_checkout.enabled: true` in `config.yml` and repo **variable**
   `ENABLE_AUTO_CHECKOUT=true`.
4. First runs are **dry runs**: the bot logs in, carts the item, walks to
   order review, then stops and notifies you. Only after you set repo
   variable `CONFIRM_PURCHASE=true` will it click "Place Order".
5. `auto_checkout.max_price_usd` in `config.yml` caps what it will spend.

Checkout selectors are best-guess until a real listing exists; expect to
tune `tracker/checkout/*.py` after the first dry run.

## Local run

```bash
pip install -r requirements.txt
NTFY_TOPIC=<your-topic> python -m tracker.main
```

Tests (matcher, notify-on-transition logic, retailer parsers against canned
responses, checkout guardrails) run with:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

They also run in CI on every push (`.github/workflows/tests.yml`).

State (which listings have already been notified) lives in
`state/seen.json` and is committed back by the workflow so you aren't
re-notified every 10 minutes. Delete the file to reset.

## Tuning

- Products/keywords: `config.yml` → `products` (per-product `must_include` /
  `exclude` lists control matching; `set.search_query` is the broad search
  sent to retailers).
- Check frequency: `.github/workflows/check-stock.yml` → `cron`. GitHub's
  floor is 5 minutes and timing is best-effort; for 1–2 minute cadence,
  move the same code to Google Cloud Run + Cloud Scheduler.
