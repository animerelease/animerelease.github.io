"""MediaOCD — WooCommerce Store API scraper.

MediaOCD is the distributor storefront for Discotek, AnimEigo, Media Blasters,
Sentai discs and others. Its WooCommerce Store API is keyless and paginated and
returns everything in one JSON feed, so — unlike the manga scrapers this engine
grew from — there is no per-product page fetch and no skip-cache to maintain:
each run rebuilds this source's rows from the live feed (SOURCES.md, Tier 1).

Field notes (probed live, see SOURCES.md):
  - prices are in minor units ("7995" = $79.95) — not tracked here yet.
  - `sku` is an internal distributor catalog code (ES459), NOT a UPC; MediaOCD
    exposes no barcode, so Info.upc is left blank and Info.catalog carries sku.
  - `brands[].name` is the distributor (Discotek, …) -> Info.publisher.
  - `categories` give the content type (Anime) and disc format (Blu-ray / DVD /
    4K UHD) plus Pre-Orders.
  - the street date and disc region live only in prose — `short_description`
    ("Expected in mid-August") and `description` ("… Region A") — so both are
    parsed defensively.
"""
import html
import re
import warnings

from session import Session
from utils import Info, Series, extract_release_date

NAME = 'MediaOCD'

API = 'https://mediaocd.com/wp-json/wc/store/v1/products'
PER_PAGE = 100
MAX_PAGES = 50  # backstop; the feed is ~4 pages at per_page=100

# only the content category we cover; excludes Live Action / Western Animation /
# Tokusatsu / Books that share the same store
ANIME_SLUG = 'anime'
# disc-format category slug -> canonical Format string (utils.DISC_FORMATS),
# widest first so a combo release resolves to its highest format
FORMAT_BY_SLUG = (
    ('4k-uhd', '4K UHD'),
    ('bluray', 'Blu-ray'),
    ('dvd', 'DVD'),
)
# fallback: format token in the product name ("… – Blu-ray")
FORMAT_IN_NAME = (
    (re.compile(r'\b4k\b|\buhd\b', re.I), '4K UHD'),
    (re.compile(r'blu[- ]?ray', re.I), 'Blu-ray'),
    (re.compile(r'\bdvd\b', re.I), 'DVD'),
)
# trailing "… – Blu-ray" / "… - DVD" / "… (4K UHD)" disc suffix to drop from the
# display title (the format is tracked separately)
NAME_FORMAT_SUFFIX = re.compile(
    r'\s*[\(\[–—:-]+\s*'
    r'(?:blu[- ]?ray(?:\s*[/+&]\s*dvd)?|dvd|4k\s*(?:ultra\s*)?(?:uhd|hd)?|uhd|combo(?:\s*pack)?)'
    r'\s*[\)\]]?\s*$', re.I)
REGION = re.compile(r'Region\s+(Free|[AB](?:\s*/\s*[AB])?|[0-9](?:\s*/\s*[0-9])?)', re.I)
STEELBOOK = re.compile(r'steel\s*book', re.I)
LIMITED = re.compile(r'limited\s*edition|collector\'?s\s*edition|deluxe\s*edition', re.I)


def disc_format(product: dict) -> str:
    slugs = {c.get('slug', '') for c in product.get('categories', ())}
    for slug, fmt in FORMAT_BY_SLUG:
        if slug in slugs:
            return fmt
    name = product.get('name', '')
    for pat, fmt in FORMAT_IN_NAME:
        if pat.search(name):
            return fmt
    return ''


def region(product: dict) -> str:
    if match := REGION.search(product.get('description', '')):
        return re.sub(r'\s+', '', match.group(1)).upper()
    return ''


def edition(name: str) -> str:
    if STEELBOOK.search(name):
        return 'SteelBook'
    if LIMITED.search(name):
        return 'LE'
    return ''


def clean_name(raw: str) -> str:
    name = html.unescape(raw).replace('’', "'").strip()
    return NAME_FORMAT_SUFFIX.sub('', name).strip()


def parse_product(product: dict) -> tuple[Series, Info] | None:
    slugs = {c.get('slug', '') for c in product.get('categories', ())}
    if ANIME_SLUG not in slugs:
        return None  # live-action / books / western animation etc.

    fmt = disc_format(product)
    if not fmt:
        warnings.warn(f'{NAME}: no disc format for {product.get("name")!r}', RuntimeWarning)
        return None

    link = product.get('permalink')
    if not link:
        return None
    name = clean_name(product.get('name', ''))
    brands = product.get('brands') or ()
    publisher = brands[0]['name'] if brands else NAME
    catalog = (product.get('sku') or '').strip()
    # street date is prose-only; the short_description holds "Expected in …",
    # so try it first and never mine the synopsis (false-positive month words)
    date = extract_release_date(product.get('short_description', ''))

    series = Series(None, name)
    info = Info(series.key, link, NAME, publisher, name, 0, fmt,
                '', catalog, region(product), edition(product.get('name', '')), date)
    return series, info


def iter_products(session: Session):
    for page in range(1, MAX_PAGES + 1):
        resp = session.get(API, params={'per_page': PER_PAGE, 'page': page})
        if resp is None or resp.status_code != 200:
            break
        try:
            products = resp.json()
        except ValueError as e:
            warnings.warn(f'{NAME}: bad JSON on page {page}: {e}', RuntimeWarning)
            break
        if not products:
            break
        yield from products
        if len(products) < PER_PAGE:
            break


def scrape_full(series: set[Series], info: set[Info]) -> tuple[set[Series], set[Info]]:
    # rebuild this source's rows from the live feed each run (the wipe guard in
    # scrape.py protects the committed data if the feed is unreachable)
    fresh: set[Info] = set()
    with Session() as session:
        for product in iter_products(session):
            try:
                parsed = parse_product(product)
            except Exception as e:
                warnings.warn(f'{NAME}: {product.get("id")}: {e}', RuntimeWarning)
                continue
            if parsed:
                s, inf = parsed
                series.add(s)
                fresh.add(inf)
    return series, fresh


def scrape(series: set[Series], info: set[Info]) -> tuple[set[Series], set[Info]]:
    return scrape_full(series, info)
