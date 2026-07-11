# data/gallery.json

Raw output of `scripts/scan_gallery.py`, refreshed daily by the
`Scan product gallery` GitHub Actions workflow. Pure data collection — it
does not drive the live status page yet (see the tracked task: "Refactor
status page: release-date schedule view grouped by set").

Shape:

```json
{
  "generated_at": "2026-07-11T19:00:00+00:00",
  "products": [
    {
      "slug": "30th-celebration-elite-trainer-box",
      "url": "https://www.pokemon.com/us/pokemon-tcg/product-gallery/30th-celebration-elite-trainer-box",
      "name": "Elite Trainer Box",
      "release_date": "2026-09-16",
      "release_date_raw": "September 16, 2026",
      "image": "https://www.pokemon.com/static-assets/.../....png",
      "set_slug": "30th-celebration",
      "set_guessed": false,
      "blocked": false,
      "error": null,
      "fetched_at": "2026-07-11T19:00:03+00:00"
    }
  ]
}
```

Notes for whoever builds the page refactor:

- `set_slug` / `set_guessed`: the product slug with its known product-type
  suffix (elite-trainer-box, mini-tin, etc.) stripped off, via
  `scripts/gallery_parse.py::derive_set_slug`. When no known suffix
  matched, `set_guessed` is `true` and the *whole* slug was used as a
  fallback "set" — treat those as low confidence and sanity-check by hand.
- `release_date` is ISO `YYYY-MM-DD` when parsing succeeded, else `null`
  with the best-effort raw text still in `release_date_raw` for a human to
  glance at.
- `blocked: true` means the page served a bot-detection challenge instead
  of content — same wall the product-gallery *listing* page always shows;
  individual product pages usually aren't walled, but this can happen.
- The scraper's slug discovery leans on pokemon.com's sitemap.xml plus any
  `gallery_slug` values already confirmed in `config.yml`. Discovery
  coverage is best-effort, not exhaustive — check the workflow logs
  (`scan-gallery.yml` run output) for what was actually attempted, and to
  see whether the "does '-169-' in image filenames mean anything" question
  has been resolved yet.
