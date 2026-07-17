"""Resolve real release dates (and ISBNs) for rows the scrapers can't date.

Some publishers simply don't publish a usable on-sale date: one_peace.py has no
date on its book pages at all, and udon.py/ablaze.py only expose "Month Year",
so their rows land as 0001-01-01 or a fake day-01. Neither Google Books (429s
without an API key) nor OpenLibrary (year-precision only) can fix that, and
Amazon needs Cloudflare credentials.

Barnes & Noble can: its product pages carry a full `datePublished` in ld+json,
and both the product page and the /s/<isbn> lookup are robots-allowed. Spot
check: Gannibal Vol. 2 -> 2024-02-14, matching the audit's ground truth.

Output is corrections.csv (headerless `isbn,date`, mirroring origins.csv), read
by parse.py so the fix survives a re-scrape -- the per-source CSVs can't hold
it, they are skip-caches that never feed info.csv.

Run:  python lnrelease/backfill.py [--limit N] [--dry-run]
Resumable: ISBNs already in corrections.csv are skipped, so a killed run just
picks up where it left off.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import re
import sys
import warnings
from pathlib import Path

from bs4 import BeautifulSoup
from session import Session

CORRECTIONS = Path('corrections.csv')
INFO = Path('info.csv')

BN_SEARCH = 'https://www.barnesandnoble.com/s/{}'
ISBN_CLEAN = re.compile(r'[^0-9X]')

# publishers whose own scraper cannot produce a real day-precision date
TARGETS = ('One Peace Books', 'Udon Entertainment', 'Denpa', 'Ablaze')


def needs_date(row: list[str]) -> bool:
    """True if this info row carries no usable day-precision date."""
    date = row[8]
    if not date or date.startswith('0001'):
        return True
    # Ablaze/Udon publish month precision only, so every day is a fake '01'
    return row[3] in ('Ablaze', 'Udon Entertainment') and date.endswith('-01')


def clean_isbn(isbn: str) -> str:
    return ISBN_CLEAN.sub('', (isbn or '').upper())


def date_from_page(content: bytes) -> tuple[str, str] | None:
    """Pull (datePublished, name) out of a B&N page's ld+json, if present."""
    soup = BeautifulSoup(content, 'lxml')
    for tag in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(tag.text)
        except (json.JSONDecodeError, TypeError):
            continue
        for node in data.get('@graph', [data]) if isinstance(data, dict) else []:
            if isinstance(node, dict) and node.get('datePublished'):
                return node['datePublished'], node.get('name', '')
    return None


def resolve(session: Session, isbn: str, links: list[str]) -> tuple[str, str] | None:
    """Try the row's own B&N product link first, then a /s/<isbn> lookup."""
    for link in links:
        if 'barnesandnoble.com' not in link:
            continue
        page = session.get(link)
        if page and (hit := date_from_page(page.content)):
            return hit
    if isbn:
        page = session.get(BN_SEARCH.format(isbn))
        if page and (hit := date_from_page(page.content)):
            return hit
    return None


def load_targets() -> list[tuple[str, str, list[str]]]:
    """(isbn, title, store_links) for each distinct undated ISBN in info.csv."""
    seen: dict[str, tuple[str, str, list[str]]] = {}
    with open(INFO, encoding='utf-8', newline='') as f:
        for row in csv.reader(f):
            if len(row) < 9 or row[3] not in TARGETS or row[2] != row[3]:
                continue
            if not needs_date(row):
                continue
            isbn = clean_isbn(row[7])
            if not isbn:
                continue  # unreachable: no ISBN to look up and no store link
            links = [a for a in row[9:] if a and 'barnesandnoble.com' in a]
            if isbn in seen:
                seen[isbn][2].extend(l for l in links if l not in seen[isbn][2])
            else:
                seen[isbn] = (isbn, row[4], list(links))
    return sorted(seen.values())


def load_done() -> dict[str, str]:
    if not CORRECTIONS.is_file():
        return {}
    with open(CORRECTIONS, encoding='utf-8', newline='') as f:
        return {r[0]: r[1] for r in csv.reader(f) if len(r) >= 2}


def save(done: dict[str, str]) -> None:
    with open(CORRECTIONS, 'w', encoding='utf-8', newline='') as f:
        csv.writer(f).writerows(sorted(done.items()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='stop after N lookups')
    ap.add_argument('--dry-run', action='store_true', help='resolve but do not write')
    args = ap.parse_args()

    targets = load_targets()
    done = load_done()
    todo = [t for t in targets if t[0] not in done]
    print(f'backfill: {len(targets)} undated ISBNs, {len(done)} already resolved, '
          f'{len(todo)} to do', flush=True)

    hits = misses = 0
    with Session() as session:
        for n, (isbn, title, links) in enumerate(todo, 1):
            if args.limit and n > args.limit:
                break
            try:
                res = resolve(session, isbn, links)
            except Exception as e:
                warnings.warn(f'({isbn}): {e}', RuntimeWarning)
                res = None
            if not res:
                misses += 1
                print(f'  [{n}/{len(todo)}] MISS {isbn} {title[:45]}', flush=True)
                continue
            raw, name = res
            try:  # B&N ld+json is ISO, but don't trust it blindly
                date = datetime.date.fromisoformat(raw[:10])
            except ValueError:
                warnings.warn(f'({isbn}): bad date {raw!r}', RuntimeWarning)
                misses += 1
                continue
            hits += 1
            done[isbn] = date.isoformat()
            print(f'  [{n}/{len(todo)}] {date} {isbn} {title[:40]:40s} | B&N: {name[:35]}',
                  flush=True)
            if not args.dry_run:
                save(done)  # incremental: a killed run keeps its progress
    print(f'backfill: {hits} resolved, {misses} unresolved, '
          f'{len(done)} total in {CORRECTIONS}', flush=True)


if __name__ == '__main__':
    sys.exit(main())
