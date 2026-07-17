import datetime
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable
from operator import attrgetter
from pathlib import Path

from parse import BOOKS
from utils import FORMATS, Book, Format, Release, Table

OUT = Path('README.md')

TAXONOMY = '''

---

## Taxonomy

**Format** is the disc type — `Blu-ray` / `DVD` / `4K UHD` (`Multi` = a release spanning more than one).

**Category** is the release type — `TV` / `movie` / `OVA` / `ONA` / `special`.

**Region** is the disc's playback region — `A` (North America) / `B` (UK & Europe) / `A/B` (region-free). A UK edition is tracked separately from its NA counterpart.

**Edition** flags a limited variant — `SteelBook` or `LE` (limited/collector's edition).

**Origin** is the production country — `JP` for the Japanese animation tracked here, with `US` / `other` for co-productions.
'''


def get_format(format: Format, github: bool) -> str:
    return str(format)


def write_page(releases: Iterable[Release], output: Path, title: str, github: bool = False,
               description: str = None) -> None:
    with open(output, 'w', encoding='utf-8') as file:
        month = 0
        year = 0
        if not github and description:
            # YAML front matter → jekyll-seo-tag emits unique <title> +
            # meta description per page (long-tail queries like
            # "<year> anime blu-ray releases"). Descriptions must not contain
            # double quotes.
            page_title = title.splitlines()[0].lstrip('#').strip()
            file.write('---\n'
                       f'title: "{page_title}"\n'
                       f'description: "{description}"\n'
                       '---\n\n')
        file.write(title)
        if not github:
            file.write('\n\n- toc\n{:toc}')
        for release in releases:
            if year != release.date.year:
                year = release.date.year
                month = 0
                header = str(year) if github else f'[{year}](/year/{year})'
                file.write(f'\n\n## {header}\n')
            if month != release.date.month:
                month = release.date.month
                file.write(f'\n### {release.date.strftime("%B")}\n\n'
                           '|Date|Title|Vol|Distributor|Format|\n'
                           '|:---:|---|:---:|---|:---:|\n')

            date = release.date.strftime('%b %d')
            name = f'[{release.name}]({release.link} "{release.publisher}")'
            format = get_format(release.format, github)
            file.write(f'|{date}|{name}|{release.volume}|{release.publisher}|{format}|\n')


def get_releases() -> list[Release]:
    dic: defaultdict[Release, list[Book]] = defaultdict(list)
    for book in sorted(Table(BOOKS, Book)):
        dic[Release(*book)].append(book)
    for release, books in dic.items():
        books.sort(key=lambda b: FORMATS.get(b.format, 0))
        formats = {Format.from_str(b.format) for b in books}
        release.format = formats.pop() if len(formats) == 1 else Format.MULTI
        release.link = books[0].link
        release.upc = books[0].upc
    return sorted(dic)


def get_current(releases: list[Release]) -> tuple[int, int]:
    today = datetime.datetime.today()
    start_date = today - datetime.timedelta(days=7)
    start_date = start_date.replace(day=1).date()
    end_date = today.replace(year=today.year+1, month=12, day=31).date()
    start = bisect_left(releases, start_date, key=attrgetter('date'))
    end = bisect_right(releases, end_date, key=attrgetter('date'), lo=start)
    return releases[start:end]


def main() -> None:
    releases = get_releases()
    current = get_current(releases)
    write_page(current,
               OUT, '# Anime Release Calendar\n\n'
               'Automated release calendar for anime on Blu-ray, DVD & 4K UHD — '
               'updated daily at [animerelease.github.io]'
               '(https://animerelease.github.io).', True)
    with open(OUT, 'a', encoding='utf-8') as file:
        file.write(TAXONOMY)
        file.write('\n\n---\n\nData engine forked from '
                   '[LNRelease](https://github.com/LNRelease/lnrelease.github.io), '
                   'the automated light novel release calendar.\n\n'
                   'Navigating this repo? See '
                   '[ARCHITECTURE.md](ARCHITECTURE.md) for the file map and '
                   'data-flow overview.\n')


if __name__ == '__main__':
    main()
