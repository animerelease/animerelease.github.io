# animerelease — source plan (revised 2026-07-17)

Priority order for scraper implementation. Endpoints below were probed live on 2026-07-17.

## Tier 1 — confirmed working, keyless

### 1. MediaOCD (Discotek, AnimEigo, Sentai discs, Media Blasters)
- **Endpoint:** `https://mediaocd.com/wp-json/wc/store/v1/products` (WooCommerce Store API, no key)
- **Verified:** returns full JSON. Prices in minor units (`"7995"` = $79.95). `sku` is an internal code (e.g. `ES459`), **not** a UPC. `brands[].name` = distributor (e.g. Discotek). `categories` include Anime / Blu-ray / Pre-Orders. Release timing sometimes only in `short_description` prose ("Expected in mid-August") — parse defensively.
- Scraper: `lnrelease/source/mediaocd.py`

### 2. Sentai Filmworks — direct store
- **Endpoint:** `https://www.sentaifilmworks.com/products.json` (Shopify, keyless, paginated)
- ⚠️ **NOT `shopsentai.com`** — that domain is dead/empty. The kickoff plan's URL is stale.
- **Verified:** works. Gold: the product `handle` is prefixed with the **UPC** (e.g. `816726029245-my-mental-choices-…`). `vendor: Sentai`, `product_type: Video`, variant `option1` = format (Blu-ray/DVD), tags carry SteelBook / Limited Edition / sub/dub. `sku` = Sentai catalog number (`SFB-MMC110`).
- Overlaps with MediaOCD's Sentai items → dedupe by UPC (Sentai side) + title/distributor match (MediaOCD side has no UPC).

### 3. AllTheAnime (Anime Limited, UK)
- **Endpoint:** `https://alltheanime.com/products.json` (Shopify, keyless)
- **Verified:** works. `vendor` includes **both** `Anime Limited` and `Crunchyroll` (UK CR releases!). `sku` = UK catalog number (`ANI1207`, `UKCR0347`). Prices GBP; **Region B**; release date/BBFC/discs only inside `body_html` prose — needs HTML parsing. No barcode/UPC in public Shopify JSON.
- June manga notes rejected it (discs only) → **valid here** for UK coverage, and partially mitigates the Crunchyroll gap (UK editions only — different UPCs/dates than NA).

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
