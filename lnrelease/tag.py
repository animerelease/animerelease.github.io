import csv
import warnings
from pathlib import Path

from scrape import INFO, SERIES
from utils import CATEGORIES, ORIGINS, Info, Series, Table

# manual overrides: key,origin,category (either may be blank); wins over
# heuristics and the JP default below
OVERRIDES = Path('origins.csv')


def load_overrides() -> dict[str, tuple[str, str]]:
    overrides = {}
    if OVERRIDES.is_file():
        with open(OVERRIDES, 'r', encoding='utf-8', newline='') as f:
            for row in csv.reader(f):
                key, origin, category = row
                if origin and origin not in ORIGINS:
                    warnings.warn(f'Unknown origin override: {row}', RuntimeWarning)
                elif category and category not in CATEGORIES:
                    warnings.warn(f'Unknown category override: {row}', RuntimeWarning)
                else:
                    overrides[key] = (origin, category)
    return overrides


def tag(series: Table, info: Table, overrides: dict[str, tuple[str, str]]) -> None:
    flagged = 0
    for s in series:
        # everything tracked here comes from the stores' Anime category, i.e.
        # Japanese animation, so origin defaults to JP; origins.csv curates the
        # exceptions (e.g. a US co-production). Category (TV/movie/OVA) is set
        # from title markers in Series.__post_init__, else defaults to TV at
        # output time (parse.py/pages.py).
        s.origin = s.origin or 'JP'

        if override := overrides.get(s.key):
            origin, category = override
            s.origin = origin or s.origin
            s.category = category or s.category

        s.flag = '' if s.origin else 'review'
        flagged += bool(s.flag)

    print(f'tag: {len(series)} series tagged, {flagged} flagged for review, '
          f'{len(overrides)} overrides', flush=True)


def main() -> None:
    series = Table(SERIES, Series)
    info = Table(INFO, Info)
    tag(series, info, load_overrides())
    series.save()


if __name__ == '__main__':
    main()
