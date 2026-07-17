"""AllTheAnime (Anime Limited, UK) — Shopify products.json scraper.

AllTheAnime's keyless products.json carries everything in body_html (SOURCES.md
Tier 2): the release date as "Release Date: dd/mm/yyyy" (UK day-first), the disc
Format, and the Region (B — this is the UK / PAL market). product_type is the
disc/edition type (Blu-ray / DVD / Steelbook / Collector's Edition), vendor is
the distributor (Anime Limited, and UK Crunchyroll editions), and sku is the
catalog number (ANI…, UKCR…). There is no UPC in the feed. Prices are out of
scope for this project and are not read.
"""
import datetime
import html
import re
import warnings

from session import Session
from utils import Info, Series

NAME = 'AllTheAnime'

API = 'https://alltheanime.com/products.json'
PRODUCT = 'https://alltheanime.com/products/{}'
LIMIT = 250
MAX_PAGES = 20

# body_html specs (run against tag-stripped text)
RELEASE = re.compile(r'Release Date\s*:?\s*(\d{1,2})/(\d{1,2})/(\d{4})', re.I)
REGION = re.compile(r'\bRegion\s*:?\s*(Free|[AB](?:\s*/\s*[AB])?|[0-9](?:\s*/\s*[0-9])?)', re.I)
FORMAT_FIELD = re.compile(r'\bFormat\s*:?\s*([A-Za-z][A-Za-z0-9 /+-]{1,18})', re.I)
STEELBOOK = re.compile(r'steel\s*book', re.I)
LIMITED = re.compile(r'limited\s*edition|collector', re.I)
# edition-type product_types that imply a Blu-ray when no explicit format is given
EDITION_TYPE = re.compile(r'steel\s*book|collector|limited|deluxe', re.I)


def body_text(body_html: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', body_html or '')
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def normalize_format(s: str) -> str:
    s = (s or '').strip().lower()
    if '4k' in s or 'uhd' in s or 'ultra hd' in s:
        return '4K UHD'
    if 'blu' in s:
        return 'Blu-ray'
    if 'dvd' in s:
        return 'DVD'
    return ''


def disc_format(product_type: str, text: str, title: str) -> str:
    if match := FORMAT_FIELD.search(text):
        if fmt := normalize_format(match.group(1)):
            return fmt
    if fmt := normalize_format(product_type):
        return fmt
    if fmt := normalize_format(title):
        return fmt
    # a Steelbook/Collector's Edition with no explicit format is a Blu-ray
    if EDITION_TYPE.search(product_type):
        return 'Blu-ray'
    return ''


def edition(product_type: str, title: str) -> str:
    text = f'{product_type} {title}'
    if STEELBOOK.search(text):
        return 'SteelBook'
    if LIMITED.search(text):
        return 'LE'
    return ''


def region(text: str) -> str:
    if match := REGION.search(text):
        return re.sub(r'\s+', '', match.group(1)).upper()
    return 'B'  # AllTheAnime is the UK / Region B market


def release_date(text: str):
    if match := RELEASE.search(text):
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return datetime.date(year, month, day)  # dd/mm/yyyy (UK)
        except ValueError:
            return None
    return None


def parse_product(product: dict) -> tuple[Series, Info] | None:
    product_type = (product.get('product_type') or '').strip()
    title = html.unescape(product.get('title', '')).replace('’', "'").strip()
    text = body_text(product.get('body_html', ''))
    fmt = disc_format(product_type, text, title)
    if not fmt:
        return None  # apparel / soundtrack / book / figure

    variants = product.get('variants') or [{}]
    catalog = (variants[0].get('sku') or '').strip()
    vendor = (product.get('vendor') or '').strip() or NAME
    link = PRODUCT.format(product.get('handle', ''))

    series = Series(None, title)
    info = Info(series.key, link, NAME, vendor, title, 0, fmt,
                '', catalog, region(text), edition(product_type, title), release_date(text))
    return series, info


def iter_products(session: Session):
    for page in range(1, MAX_PAGES + 1):
        resp = session.get(API, params={'limit': LIMIT, 'page': page})
        if resp is None or resp.status_code != 200:
            break
        try:
            products = resp.json().get('products', [])
        except ValueError as e:
            warnings.warn(f'{NAME}: bad JSON on page {page}: {e}', RuntimeWarning)
            break
        if not products:
            break
        yield from products
        if len(products) < LIMIT:
            break


def scrape_full(series: set[Series], info: set[Info]) -> tuple[set[Series], set[Info]]:
    fresh: set[Info] = set()
    with Session() as session:
        for product in iter_products(session):
            try:
                res = parse_product(product)
            except Exception as e:
                warnings.warn(f'{NAME}: {product.get("handle")}: {e}', RuntimeWarning)
                continue
            if res:
                s, inf = res
                series.add(s)
                fresh.add(inf)
    return series, fresh


def scrape(series: set[Series], info: set[Info]) -> tuple[set[Series], set[Info]]:
    return scrape_full(series, info)
