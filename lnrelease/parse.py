import csv
import datetime
import importlib
import re
import warnings
from collections import Counter, defaultdict
from itertools import groupby
from operator import attrgetter
from pathlib import Path

import publisher
from scrape import INFO, SERIES
from utils import (EPOCH, FORMATS, PRIMARY, SECONDARY, SOURCES, Book, Info,
                   Series, Table, clean_str, region_market)

# Manual date corrections: `code,date`, one per line where code is a catalog
# number or UPC (see origins.csv for the same override pattern). Needed because
# stores often give only a prose street date ("Expected in mid-August") that
# resolves to a whole-month or placeholder date. This is the durable home for
# the fix: the per-source caches never feed info.csv and a re-scrape rewrites
# it, so a correction written there would be silently undone.
CORRECTIONS = Path('corrections.csv')
CODE_CLEAN = re.compile(r'[^0-9A-Z]')

PUBLISHERS = {}
for file in Path('lnrelease/publisher').glob('*.py'):
    module = importlib.import_module(f'publisher.{file.stem}')
    PUBLISHERS[module.NAME] = module

BOOKS = Path('books.csv')


def clean_code(code: str) -> str:
    """Normalise a UPC/catalog code for matching (drop separators, upper-case)."""
    return CODE_CLEAN.sub('', (code or '').upper())


def load_corrections() -> dict[str, datetime.date]:
    if not CORRECTIONS.is_file():
        return {}
    corrections: dict[str, datetime.date] = {}
    with open(CORRECTIONS, encoding='utf-8', newline='') as f:
        for row in csv.reader(f):
            if len(row) < 2 or not row[0].strip():
                continue
            try:
                corrections[clean_code(row[0])] = datetime.date.fromisoformat(row[1].strip())
            except ValueError:
                warnings.warn(f'{CORRECTIONS}: bad row {row}', RuntimeWarning)
    return corrections


def main() -> None:
    series = {row.key: row for row in Table(SERIES, Series)}
    info = Table(INFO, Info)
    # publishers that produced at least one primary-source row this run. A
    # PRIMARY publisher's aggregator (SECONDARY) copies are normally dropped as
    # duplicates of its own scraper's rows -- but only when that scraper
    # actually ran. If it produced nothing (e.g. Kodansha/VIZ/TOKYOPOP, whose
    # only rows come from PRH/Crunchyroll), keep the aggregator copies instead
    # of dropping the publisher entirely.
    scraped_pubs = {i.publisher for i in info if i.source not in SECONDARY}
    # Apply date corrections here, before any Book is built, so the corrected
    # date flows through publisher.parse(), the sort, and the dedup rather than
    # being patched onto the output. Safe to mutate in place: Info hashes on
    # (link, format), not date.
    corrections = load_corrections()
    fixed = 0
    for i in info:
        date = corrections.get(clean_code(i.catalog)) or corrections.get(clean_code(i.upc))
        if date and i.date != date:
            i.date = date
            fixed += 1
    if corrections:
        print(f'parse: {fixed} dates corrected from {CORRECTIONS} '
              f'({len(corrections)} overrides)', flush=True)

    links: defaultdict[str, list[Info]] = defaultdict(list)
    lst: list[Info] = []
    for i in info:
        links[i.link].append(i)
        redundant = (i.source in SECONDARY and i.publisher in PRIMARY
                     and i.publisher in scraped_pubs)
        if not redundant:
            lst.append(i)
    lst.sort()
    # sort by source then title
    links = dict(sorted(links.items(), key=lambda x: (SOURCES[x[1][0].source], x[1][0].title)))
    BOOKS.unlink(missing_ok=True)
    books = Table(BOOKS, Book)

    for key, group in groupby(lst, attrgetter('serieskey', 'publisher')):
        serieskey = key[0]
        serie = series[serieskey]
        pub = key[1]
        # anime distributors (Discotek, Sentai, …) have no per-publisher module;
        # they use the generic parser, so this fallback is the normal path here,
        # not an anomaly worth warning about
        module = PUBLISHERS.get(pub, publisher)
        inf: defaultdict[str, list[Info]] = defaultdict(list)
        for i in group:
            inf[i.format].append(i)
        inf = dict(sorted(inf.items(), key=lambda x: FORMATS.get(x[0], 0)))
        for x in module.parse(serie, inf, links).values():
            books.update(x)

    for book in books:
        if serie := series.get(book.serieskey):
            # unresolved series default to the JP / TV-series base rate
            book.origin = serie.origin or 'JP'
            book.category = serie.category or 'TV'

    merge_editions(books)
    books.save()


def _find(parent: list[int], x: int) -> int:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def merge_editions(books: Table) -> None:
    """Collapse the same physical release listed more than once -- across series
    keys within a store, or across stores -- to a single row.

    Rows are unioned when they share any identity signal: a UPC, a normalized
    distributor catalog code, or a (normalized title, format, region-market,
    edition) tuple. That last signal lets a MediaOCD row (no UPC) merge with the
    Sentai listing of the same disc (which has one); the UPC/catalog signals
    catch pairs whose titles differ between stores. A UK/Region-B edition never
    merges with its NA counterpart (different market).

    The surviving row prefers a real date and a real UPC, then the most-
    consolidated series key, and is enriched in place with the date/UPC/region
    from whichever store in the cluster supplied them -- so a MediaOCD street
    date and a Sentai UPC end up on the same row.
    """
    lst = list(books)
    signals: defaultdict[tuple, list[int]] = defaultdict(list)
    for i, b in enumerate(lst):
        if b.upc:
            signals[('upc', b.upc)].append(i)
        if b.catalog:
            signals[('cat', clean_code(b.catalog))].append(i)
        signals[('tfr', clean_str(b.name), b.format,
                 region_market(b.region), b.edition)].append(i)

    parent = list(range(len(lst)))
    for ids in signals.values():
        for j in ids[1:]:
            parent[_find(parent, j)] = _find(parent, ids[0])

    clusters: defaultdict[int, list[Book]] = defaultdict(list)
    for i, b in enumerate(lst):
        clusters[_find(parent, i)].append(b)

    keycount = Counter(b.serieskey for b in lst)
    for group in clusters.values():
        if len(group) < 2:
            continue
        canon = max(group, key=lambda b: (b.date != EPOCH, bool(b.upc),
                                          keycount[b.serieskey], -len(b.serieskey)))
        if not canon.upc:
            canon.upc = next((b.upc for b in group if b.upc), '')
        if canon.date == EPOCH:
            real = [b.date for b in group if b.date != EPOCH]
            if real:
                canon.date = min(real)
        if not canon.region:
            canon.region = next((b.region for b in group if b.region), '')
        for b in group:
            if b is not canon:
                books.discard(b)


if __name__ == '__main__':
    main()
