---
name: fetch-sku-images
description: Run when the user says there's a new 30th Celebration SKU, asks to fetch/refresh product images, or wants the "Fetch SKU images" GitHub Actions workflow triggered for zfand/Pok-mon-Stock-Tracker. Runs the workflow, waits for it, and reports which products got a real image vs. are still on placeholder art — plus offers to wire in any newly-confirmed slug or newly-discovered SKU.
---

You're operating the Pokémon 30th Celebration stock tracker repo
(`zfand/Pok-mon-Stock-Tracker`). The user runs this skill after they notice
(by whatever means — a new entry in `data/gallery.json`, checking
pokemon.com themselves, etc.) that there's a new or previously-unresolved
SKU that needs a real product image instead of the generated placeholder
art in `docs/img/`.

**Branch**: `claude/pokemon-tcg-preorder-app-xxysm0` — this is also the
repo's default branch (there is no separate `main`).

## Steps

1. **Trigger the workflow.** Use the GitHub MCP tools if they're loaded in
   this session (search for them first: `ToolSearch` with query
   `"select:mcp__github__actions_run_trigger,mcp__github__actions_list,mcp__github__get_job_logs"`).
   Call `mcp__github__actions_run_trigger` with `method: "run_workflow"`,
   `owner: "zfand"`, `repo: "Pok-mon-Stock-Tracker"`,
   `workflow_id: "fetch-images.yml"`, `ref: "claude/pokemon-tcg-preorder-app-xxysm0"`.

   If GitHub MCP tools aren't available in this environment, fall back to
   the `gh` CLI via Bash:
   `gh workflow run fetch-images.yml --repo zfand/Pok-mon-Stock-Tracker --ref claude/pokemon-tcg-preorder-app-xxysm0`

2. **Wait for it to finish.** It's a short job (~30-60s: pip install +
   probing each product's CDN URL). Poll `mcp__github__actions_list`
   (`method: "list_workflow_runs"`, `resource_id: "fetch-images.yml"`,
   `per_page: 1`) or `gh run list --workflow=fetch-images.yml --limit 1`
   until `status` is `completed`. Don't sleep-loop faster than every
   ~15-20s.

3. **Read the run's log** (`mcp__github__get_job_logs` with
   `return_content: true`, or `gh run view --log`) and summarize plainly:
   - Which product IDs got `MATCH — saved docs/img/<id>.png` (a real image
     just landed, or was refreshed).
   - Which are still unresolved (every candidate slug 403'd — still on
     placeholder art).
   - **Important**: the CDN image slug isn't always identical to the
     product's gallery-page slug (`gallery_slug`) — confirmed cases so far
     drop either "-celebration-" or "-and-" from the page slug. When a
     product has no `image_slug` set, the script auto-tries both
     transformations of `gallery_slug` as fallbacks. If one hits, the log
     prints `^ add this to config.yml as: image_slug: "<slug>"` — when you
     see that, actually make the edit (add an `image_slug:` field right
     after that product's `gallery_slug:` line in `config.yml`), commit,
     and push. This makes the match durable: without it, next run has to
     re-derive it instead of downloading directly. (A candidate guess from
     `CANDIDATES` matching for a product with no `gallery_slug` at all logs
     the same way but as `gallery_slug: "<slug>"` instead.)

4. **Check for genuinely new SKUs**, not just new images for known
   products. Read `data/gallery.json` and look at products with
   `set_slug` containing `"30th-celebration"`. Compare their `slug` against
   every product's `gallery_slug` already in `config.yml`. If you find one
   in `gallery.json` that isn't represented in `config.yml` at all, that's
   a genuinely new SKU the tracker doesn't know about yet — tell the user
   what it looks like (name/slug/release_date if resolved) and ask whether
   to add it as a new product entry in `config.yml` (with `alert: false`,
   `purchase: false` by default, matching how every other non-ETB product
   started out — see existing entries for the shape). Don't add it
   unprompted; this changes what the tracker actively watches and alerts
   on, so confirm first.

5. **No manual Pages redeploy needed** — `pages.yml` listens on this
   workflow's completion via `workflow_run` and redeploys automatically
   once it succeeds. Just mention that the site will pick up the change on
   its own within a few minutes; don't trigger `pages.yml` yourself.

Report back concisely: what changed, what's still unresolved, and what (if
anything) you did to `config.yml`.
