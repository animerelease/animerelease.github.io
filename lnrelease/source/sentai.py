"""Sentai Filmworks — Shopify products.json scraper.

Sentai's direct store exposes a keyless, paginated products.json (SOURCES.md
Tier 2). The gold here is the UPC: it is the 12-13 digit prefix of the product
`handle` (e.g. 816726029245-my-mental-choices-…). vendor is 'Sentai',
product_type 'Video' (merch/apparel is skipped), variant option1 is the disc
format, sku is the catalog number (SFB-…), and tags carry the edition and
sub/dub. Region is NA (Region A).

The street date is NOT in products.json, so it is enriched from each product
page (a `<span class="releasedate">September 29, 2026</span>`). Those pages are
rate-limited, so a skip-cache (sentai.csv, link->date) persists resolved dates
across runs and each run spends at most SENTAI_DATE_SECONDS fetching, pre-orders
first (their upcoming dates matter most). Rows whose date is still unknown fall
back to the 0001-01-01 sentinel.
"""
import html
import os
import re
import warnings
from pathlib import Path
from time import monotonic

from session import Session
from utils import Info, Key, Series, Table, extract_release_date

NAME = 'Sentai Filmworks'

API = 'https://www.sentaifilmworks.com/products.json'
PRODUCT = 'https://www.sentaifilmworks.com/products/{}'
PAGES = Path('sentai.csv')  # skip-cache: product link -> resolved release date
LIMIT = 250
MAX_PAGES = 10
# per-run budget for product-page date fetches; the cache persists dates so
# later runs need not refetch back-catalogue. 0 disables page fetches entirely.
DATE_SECONDS = int(os.getenv('SENTAI_DATE_SECONDS', '120'))

UPC_PREFIX = re.compile(r'^(\d{12,13})-')
RELEASE_DATE = re.compile(r'class="releasedate">\s*([^<]+?)\s*<', re.I)
STEELBOOK = re.compile(r'steel\s*book', re.I)
LIMITED = re.compile(r'limited\s*edition|collector', re.I)
FORMAT_MAP = {
    'blu-ray': 'Blu-ray', 'bluray': 'Blu-ray', 'blu ray': 'Blu-ray',
    'dvd': 'DVD',
    '4k uhd': '4K UHD', '4k ultra hd': '4K UHD', 'uhd': '4K UHD', '4k': '4K UHD',
}


def upc_from_handle(handle: str) -> str:
    match = UPC_PREFIX.match(handle or '')
    return match.group(1) if match else ''


def disc_format(variant: dict, tags: list[str]) -> str:
    opt = (variant.get('option1') or '').strip().lower()
    if opt in FORMAT_MAP:
        return FORMAT_MAP[opt]
    for tag in tags:
        if (t := tag.strip().lower()) in FORMAT_MAP:
            return FORMAT_MAP[t]
    return ''


def edition(title: str, tags: list[str]) -> str:
    text = title + ' ' + ' '.join(tags)
    if STEELBOOK.search(text):
        return 'SteelBook'
    if LIMITED.search(text):
        return 'LE'
    return ''


def is_preorder(tags: list[str]) -> bool:
    return any('preorder' in t.lower().replace('-', '') or 'preflag' in t.lower().replace('-', '')
               for t in tags)


def parse_product(product: dict) -> tuple[Series, Info] | None:
    if product.get('vendor') != 'Sentai' or product.get('product_type') != 'Video':
        return None  # merch / apparel / soundtrack
    variants = product.get('variants') or [{}]
    tags = product.get('tags') or []
    fmt = disc_format(variants[0], tags)
    if not fmt:
        return None

    handle = product.get('handle', '')
    title = html.unescape(product.get('title', '')).replace('’', "'").strip()
    catalog = (variants[0].get('sku') or '').strip()
    link = PRODUCT.format(handle)

    series = Series(None, title)
    info = Info(series.key, link, NAME, NAME, title, 0, fmt,
                upc_from_handle(handle), catalog, 'A', edition(title, tags), None)
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


def fetch_date(session: Session, link: str):
    resp = session.get(link)
    if resp is None or resp.status_code != 200:
        return None
    if match := RELEASE_DATE.search(resp.text):
        return extract_release_date(match.group(1))
    return None


def scrape_full(series: set[Series], info: set[Info]) -> tuple[set[Series], set[Info]]:
    cache = Table(PAGES, Key)
    cached = {row.key: row.date for row in cache}  # link -> date (may be None)
    parsed: list[tuple[Info, bool]] = []

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
                parsed.append((inf, is_preorder(product.get('tags') or [])))

        for inf, _ in parsed:
            if date := cached.get(inf.link):
                inf.date = date

        # date enrichment: pre-orders every run (cheap, dates move), then
        # not-yet-cached back-catalogue, within the time budget
        if DATE_SECONDS > 0:
            todo = ([inf for inf, pre in parsed if pre]
                    + [inf for inf, pre in parsed if not pre and inf.link not in cached])
            deadline = monotonic() + DATE_SECONDS
            done = 0
            for inf in todo:
                if monotonic() >= deadline:
                    break
                date = fetch_date(session, inf.link)
                inf.date = date or inf.date
                cache.discard(Key(inf.link, None))
                cache.add(Key(inf.link, date))
                done += 1
            warnings.warn(f'{NAME}: resolved {done}/{len(todo)} product-page dates '
                          f'this run', RuntimeWarning)

    cache.save()
    return series, {inf for inf, _ in parsed}


def scrape(series: set[Series], info: set[Info]) -> tuple[set[Series], set[Info]]:
    return scrape_full(series, info)
