import datetime
import json
import os
import re
import warnings
from pathlib import Path
from random import random
from time import monotonic

from bs4 import BeautifulSoup
from session import Session
from utils import Info, Key, Series, Table

NAME = 'Square Enix'

HOST = 'https://squareenixmangaandbooks.square-enix-games.com'
SERIES = re.compile('/series/')
# incremental skip-cache: SE has no incremental refresh and 30-600s per-request
# delays, so a full crawl never finishes. Cache each series/volume page by date
# and skip settled (past-dated) pages on later runs, re-checking a random 20%.
PAGES = Path('square_enix.csv')
# Per-run wall-clock budget. The catalogue is ~78 series / ~470 pages at a
# ~315s mean delay (~41h), so a run MUST stop early and resume next time. The
# budget has to expire before scrape.py's global SCRAPE_TIMEOUT: on that
# timeout scrape.py abandons the unresolved future, discarding every row this
# source scraped, so an unbounded run contributes nothing no matter how long it
# ran. 0 = unbounded (manual full crawls).
BUDGET_SECONDS = int(os.getenv('SE_BUDGET_SECONDS', '0'))


def get_format(s: str) -> str:
    match s:
        case ('Paperback'
              | 'Trade Paperback'):
            return 'Paperback'
        case ('Hardcover'):
            return 'Hardcover'
        case ('Digital'):
            return 'Digital'
        case ('Chapters (Digital)'):
            return None
        case _:
            warnings.warn(f'Unknown SE format: {s}', RuntimeWarning)
            return None


def parse(session: Session, series: Series, link: str, index: int) -> set[Info]:
    page = session.get(link)
    soup = BeautifulSoup(page.content, 'lxml')
    jsn = json.loads(soup.find('script', type='application/ld+json').text)
    title = jsn['name']
    date = datetime.datetime.strptime(jsn['datePublished'], '%B %d, %Y').date()
    info = set()
    for i, work in enumerate(jsn['workExample']):
        format = get_format(work['bookEdition'])
        if not format:
            continue
        isbn = work['isbn'] if i == 0 else ''
        info.add(Info(series.key, link, NAME, NAME, title, index, format, isbn, date))
    return info


def scrape_full(series: set[Series], info: set[Info], limit: int = 0) -> tuple[set[Series], set[Info]]:
    pages = Table(PAGES, Key)
    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=365)
    # settled pages (past-dated, seen before) are skipped 80% of the time
    skip = {row.key for row in pages if random() > 0.2 and row.date and row.date < cutoff}

    deadline = monotonic() + BUDGET_SECONDS if BUDGET_SECONDS else None
    with Session() as session:
        page = session.get(f'{HOST}/en-us/series')
        soup = BeautifulSoup(page.content, 'lxml')
        lst = soup.find_all('a', href=SERIES)
        kept = 0
        spent = False
        for x in lst:
            title = x.find(class_='p-1').text
            if '(Light Novel)' in title or '(Novel)' in title:
                continue
            link = f'{HOST}{x["href"]}'
            if link in skip:  # whole series settled -> skip its series + volume fetches
                continue
            if limit and kept >= limit:
                break
            if deadline and monotonic() >= deadline:
                spent = True
                break
            kept += 1
            try:
                page = session.get(link)
                soup = BeautifulSoup(page.content, 'lxml')
                volumes = soup.select('div:has(div:-soup-contains("VOLUMES")) > a')
                serie = Series(None, title)
                latest = None
                for index, volume in enumerate(volumes, 1):
                    vlink = f'{HOST}{volume["href"]}'
                    if vlink in skip:
                        continue
                    if deadline and monotonic() >= deadline:
                        spent = True
                        break
                    try:
                        inf = parse(session, serie, vlink, index)
                    except Exception as e:
                        # isolate the volume: a malformed page (e.g. missing
                        # datePublished) must not abandon the rest of the
                        # series, or it re-fetches from scratch every run
                        warnings.warn(f'({vlink}): {e}', RuntimeWarning)
                        continue
                    if inf:
                        series.add(serie)
                        info.update(inf)
                        vdate = next(iter(inf)).date
                        pages.discard(Key(vlink, vdate))
                        pages.add(Key(vlink, vdate))
                        if latest is None or vdate > latest:
                            latest = vdate
                # cache the series by its newest volume date so settled series
                # (all volumes released long ago) can be skipped wholesale later.
                # Only when the series was walked to the end -- a budget-cut
                # series still has unfetched volumes, so caching it here would
                # let a later run skip them and never finish the series.
                if latest and not spent:
                    pages.discard(Key(link, latest))
                    pages.add(Key(link, latest))
            except Exception as e:
                warnings.warn(f'({link}): {e}', RuntimeWarning)
            # persist per series: the run is expected to be cut short (budget or
            # SCRAPE_TIMEOUT), and an end-of-crawl save would lose the whole
            # run's progress -- which is why this cache never populated at all
            pages.save()
            if spent:
                break
        print(f'{NAME}: {kept} of {len(lst)} series kept'
              f'{" (budget spent, resuming next run)" if spent else ""}',
              flush=True)

    pages.save()
    return series, info
