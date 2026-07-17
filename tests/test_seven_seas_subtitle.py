"""Seven Seas comma-in-subtitle volume parsing (AUDIT task 5a).

The audit reported that a Seven Seas subtitle containing a comma leaked into the
volume field: "The Cursed Sword Master's Harem Life: By the Sword, For the
Sword" stored volume = "For the Sword". A grep of the current dataset finds zero
non-numeric Seven Seas volumes and the cited series parses to volumes 1..8, so
the defect is not reproducible through the present code (it predates the
post-audit parse.py changes). This is a regression guard pinning the correct
behaviour: comma subtitles stay in the name, volumes stay numeric.
"""
import datetime

from utils import Info, Series
import publisher.seven_seas as ss


def build(base: str, n: int) -> dict:
    date = datetime.date(2024, 1, 1)
    return {'Physical': [
        Info(Series(None, base).key, f'http://x/{v}', ss.NAME, ss.NAME,
             f'{base} Vol. {v}', v, 'Physical', f'97800000000{v:02d}', date)
        for v in range(1, n + 1)
    ]}


def parse(base: str, n: int) -> list:
    series = Series(None, base)
    books = ss.parse(series, build(base, n), {})
    return sorted((b for lst in books.values() for b in lst if b),
                  key=lambda b: int(b.volume))


class TestCommaSubtitle:
    BASE = "The Cursed Sword Master's Harem Life: By the Sword, For the Sword"

    def test_volumes_are_numeric_and_sequential(self):
        vols = [b.volume for b in parse(self.BASE, 8)]
        assert vols == [str(i) for i in range(1, 9)]

    def test_subtitle_stays_in_name(self):
        for b in parse(self.BASE, 8):
            assert b.name == self.BASE
            assert 'For the Sword' not in b.volume

    def test_single_comma_subtitle_volume(self):
        # a lone volume must not fall back to splitting the subtitle
        [book] = parse('Title: First Part, Second Part', 1)
        assert book.volume == '1'
        assert book.name == 'Title: First Part, Second Part'
