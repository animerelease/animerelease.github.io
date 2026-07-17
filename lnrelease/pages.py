import datetime
import json
from bisect import bisect_right
from operator import attrgetter
from pathlib import Path

from scrape import SERIES
from utils import Format, Series, Table
from write import get_current, get_releases, write_page

HTML = Path('html.md')
YEAR = Path('year')
DATA = Path('data.json')


def main() -> None:
    releases = get_releases()
    current = get_current(releases)

    title = 'Manga Releases'
    scope = 'licensed English manga, manhwa, manhua & webtoons'
    # all anime disc releases are physical, so there is no per-format split;
    # html.md is the full non-JS calendar (the noscript target)
    write_page(current,
               HTML, f'# Licensed {title}',
               description=f'Full release calendar for {scope} — '
                           'every upcoming volume with date, series, '
                           'publisher and format, updated daily.')

    YEAR.mkdir(exist_ok=True)
    start = 0
    while start < len(releases):
        year = releases[start].date.year
        end_date = datetime.datetime(year, 12, 31).date()
        end = bisect_right(releases, end_date, key=attrgetter('date'), lo=start)
        write_page(releases[start:end], YEAR/f'{year}.md', f'# {year} {title}',
                   description=f'{year} release calendar for {scope} — '
                               f'every volume released in {year} with '
                               'date, series, publisher and format.')
        start = end

    releases.sort(key=lambda x: x.serieskey)
    table = {x.key: x for x in Table(SERIES, Series)}
    series = {x: i for i, x in enumerate(sorted({x.serieskey for x in releases}))}
    publishers = {x: i for i, x in enumerate(sorted({x.publisher for x in releases}))}
    formats = {x: i for i, x in enumerate(Format)}
    # data rows keep indices 0-7 (series, link, publisher, name, volume, format,
    # code, date) stable for the existing table script; the new disc fields
    # (catalog, region, edition) are appended at 8-10. The code slot carries the
    # UPC when known, else the distributor catalog number.
    jsn = {'series': [[key, table[key].title,
                       table[key].origin or 'JP', table[key].category or 'TV']
                      for key in series],
           'publishers': list(publishers),
           'data': [[series[x.serieskey],
                x.link,
                publishers[x.publisher],
                x.name,
                x.volume,
                formats[x.format],
                x.upc or x.catalog,
                str(x.date),
                x.catalog,
                x.region,
                x.edition,
                ] for x in releases]}
    with open(DATA, 'w') as file:
        json.dump(jsn, file, separators=(',', ':'))


if __name__ == '__main__':
    main()
