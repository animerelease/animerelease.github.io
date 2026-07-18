# animerelease — source plan (revised 2026-07-17)

Priority order for scraper implementation. Endpoints below were probed live on 2026-07-17.

## Tier 1 — confirmed working, keyless

### 1. MediaOCD (Discotek, AnimEigo, Sentai discs, Media Blasters)
- **Endpoint:** `https://mediaocd.com/wp-json/wc/store/v1/products` (WooCommerce Store API, no key)
- **Verified:** returns full JSON. Prices in minor units (`"7995"` = $79.95). `sku` is an internal code (e.g. `ES459`), **not** a UPC. `brands[].name` = distributor (e.g. Discotek). `categories` include Anime / Blu-ray / Pre-Orders. Release timing sometimes only in `short_description` prose ("Expected in mid-August") — parse defensively.
- **Status: BUILT** — `lnrelease/source/mediaocd.py` (pass 1). ~299 anime rows.

### 2. Sentai Filmworks — direct store
- **Endpoint:** `https://www.sentaifilmworks.com/products.json` (Shopify, keyless, paginated)
- ⚠️ **NOT `shopsentai.com`** — that domain is dead/empty. The kickoff plan's URL is stale.
- **Verified:** works. Gold: the product `handle` is prefixed with the **UPC** (e.g. `816726029245-my-mental-choices-…`). `vendor: Sentai`, `product_type: Video`, variant `option1` = format (Blu-ray/DVD), tags carry SteelBook / Limited Edition / sub/dub. `sku` = Sentai catalog number (`SFB-MMC110`).
- Overlaps with MediaOCD's Sentai items → dedupe by UPC (Sentai side) + title/distributor match (MediaOCD side has no UPC).
- **Status: BUILT** — `lnrelease/source/sentai.py` (pass 2). ~382 rows, ~95% with UPC. The street date is **not** in products.json; it is scraped from each product page (`<span class="releasedate">`) into a `sentai.csv` skip-cache within a per-run `SENTAI_DATE_SECONDS` budget, pre-orders first. The MediaOCD/Sentai overlap (~38 titles) merges correctly, keeping the Sentai UPC.

### 3. AllTheAnime (Anime Limited, UK)
- **Endpoint:** `https://alltheanime.com/products.json` (Shopify, keyless)
- **Verified:** works. `vendor` includes **both** `Anime Limited` and `Crunchyroll` (UK CR releases!). `sku` = UK catalog number (`ANI1207`, `UKCR0347`). Prices GBP; **Region B**; release date/BBFC/discs only inside `body_html` prose — needs HTML parsing. No barcode/UPC in public Shopify JSON.
- June manga notes rejected it (discs only) → **valid here** for UK coverage, and partially mitigates the Crunchyroll gap (UK editions only — different UPCs/dates than NA).
- **Status: BUILT** — `lnrelease/source/alltheanime.py` (pass 2). ~1569 rows, ~93% dated from `body_html` (`Release Date: dd/mm/yyyy`, UK day-first), region defaults to B, `product_type` gives format/edition. Vendor `Crunchyroll` yields ~150 UK CR editions. Kept as a distinct **Region-B/UK market** — never merges with an NA release of the same title.

### 4. Sugoi Shop (Sugoi Co, AU/NZ) — NOT BUILT YET
- **Endpoint:** `https://sugoi.shop/products.json` (Shopify, keyless) — verified live 2026-07-17.
- Sugoi Co = the AU/NZ anime distributor founded 2023 by ex-Madman Anime people (incl. co-founder Tim Anderson) after the Aniplex/Crunchyroll takeover. Their shop carries their disc releases (e.g. Cyberpunk Edgerunners CE, Colorful Stage movie CE).
- ⚠️ Quirks: `product_type` is `"DVD"` even for Blu-ray collector's editions — derive format from **collection membership** (`/collections/blu-ray/`, `/collections/dvd/`, `/collections/blu-ray-4k/`, `/collections/pre-order-dvd-blu-ray/`) or title, not product_type. `vendor` = "Sugoi Shop" (not distributor). `sku` internal (`SV…`), no UPC. No street date in feed — pre-order collection + page check needed.
- **This adds the third English market: AU/NZ** (alongside NA and UK).

## Australia market notes (2026-07-17)

- **Madman no longer does anime.** Madman Anime Group sold to Aniplex (2019) → renamed Crunchyroll Pty Ltd (2022) → store became **Crunchyroll Store Australia** (Jan 2023). Madman's own `shop.madman.com.au` (Shopify, feed works) is films-only — zero anime/manga collections, confirmed via collections.json.
- **Crunchyroll Store AU** (`crunchyroll.com.au`): probe returned empty (custom/legacy platform, not Shopify). Same ownership as the paywalling US store — treat with the same caution. Candidate only.
- ⚠️ **Market must come from the source store, not the disc region:** UK and AU are both Region B. AllTheAnime→UK, Sugoi→AU/NZ, US stores→NA. The current `region_market` heuristic (B→UK) breaks the moment Sugoi lands — fix it as part of that pass.

## Parked — Crunchyroll store ⚠️

**Do not build crunchyroll.py adaptation now.** Announced 2026-07-14:

1. **Paywall:** store goes Mega/Ultimate Fan members-only starting **August 2026** (gift cards sunset Aug 14). Scraping behind a paid login conflicts with the polite-scraper design and ToS.
2. **Catalog gutted:** hundreds of Blu-ray/manga sets already delisted; pivot to "collectibles, curated drops, limited-release products" → no longer a comprehensive disc catalog even if reachable.
3. **Replatform risk:** existing `crunchyroll.py` rides the SFCC/Mobify SLAS guest-token endpoint (`/mobify/slas/private/shopper/auth/...`); the "brand-new shopping experience" will likely break it.

**Coverage gap this creates:** Crunchyroll's own NA disc releases — the largest NA distributor. Mitigations, in order:
- AllTheAnime for CR **UK** editions (already Tier 1).
- Amazon thin scrape (already planned last) becomes the NA fallback for CR + Aniplex exclusives.
- Re-evaluate at new-store launch (Aug 2026): if a public unauthenticated product-search API survives, revisit.

## Candidates — unverified

| Source | Status | Notes |
|---|---|---|
| Shout! Factory / Shout Studios | `products.json` probe returned empty | Would cover GKIDS/Ghibli + Shout anime. Verify via browser (may be bot-walled or non-Shopify). |
| GKIDS (shop.gkids.com) | probe returned empty | Same — distribution runs through Shout anyway. |
| animecornerstore.com | not probed | Claims to stock every NA anime disc; legacy custom site, likely painful. Could plug the CR-NA gap. |
| Bull Moose / DeepDiscount / Zavvi US / Poggers | not probed | General retailers; evaluate only if the CR-NA gap stays open post-August. |

## Data-model implications

- **UPC/EAN:** primary key where available (Sentai handles). MediaOCD + AllTheAnime don't expose it → schema must allow null UPC + catalog number (`ES459`, `SFB-MMC110`, `ANI1207`, `UKCR0347`).
- **Region column** (A/B, or market US/UK) — needed now that AllTheAnime is Tier 1.
- Release dates sometimes prose-only (`short_description` / `body_html`) → shared date-extraction helper.

## Cross-store merge (pass 2)

`parse.merge_editions` unions rows sharing a UPC, a normalized catalog code, or
`(normalized title, format, region-market, edition)`, then keeps one row per
cluster — preferring a real date and a real UPC and enriching those fields in
place. A MediaOCD row (no UPC) thus inherits the Sentai UPC of the same disc,
and a UK/Region-B edition never merges with its NA counterpart. `region_market`
buckets B/2/PAL → UK, region-free (A/B, Free) → its own bucket, everything else
→ NA. `Book`/`Release` identity includes region + edition so distinct editions
don't collide in the CSV set before the merge runs.

## Date coverage (date-gap investigation, pass 2)

After pass 2, **~68% of rows carry a real date** (up from ~12% MediaOCD-only):
AllTheAnime `body_html` dates ~93% of its rows, Sentai product-page dates fill
in over runs, and the merge propagates a store's date onto its no-date twin.

**MediaOCD back-catalogue has no recoverable street date.** Probed the product
permalink pages (2026-07-17): no JSON-LD `releaseDate`/`availabilityStarts`, no
"Release Date"/"Street Date" text, no prose date — the "Expected in …" line
exists only on pre-orders (already parsed from `short_description`). So **no
MediaOCD page-enrichment step was added**; those ~260 back-catalogue rows keep
the `0001-01-01` sentinel.

**Historical dates need an external source.** Candidate: the **ANN (Anime News
Network) Encyclopedia XML API** (`cdn.animenewsnetwork.com/encyclopedia/api.xml`),
which lists home-video release dates per title — a future pass could match by
normalized title/UPC and backfill sentinels. Left as sentinels for now.
