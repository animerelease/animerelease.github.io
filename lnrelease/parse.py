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
from utils import FORMATS, PRIMARY, SECONDARY, SOURCES, Book, Info, Series, Table

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

    # collapse the same edition appearing more than once across series keys (a
    # title split under an aggregator and a direct-store key). A UPC (or, when
    # absent, the distributor catalog number) plus format identifies exactly one
    # edition, so keep a single row per (code, format) -- on the key that carries
    # the most volumes (the consolidated series). Rows with no code at all are
    # left alone rather than collapsed together on an empty key.
    by_edition: defaultdict[tuple[str, str], list[Book]] = defaultdict(list)
    for book in books:
        code = book.upc or book.catalog
        if code:
            by_edition[(code, book.format)].append(book)
    keycount = Counter(book.serieskey for book in books)
    for dupes in by_edition.values():
        if len(dupes) > 1:
            canon = max(dupes, key=lambda b: (keycount[b.serieskey], -len(b.serieskey)))
            for b in dupes:
                if b is not canon:
                    books.discard(b)

    books.save()


if __name__ == '__main__':
    main()
