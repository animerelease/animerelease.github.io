"""Word-number volume parsing (AUDIT task 5b).

"Volume One" must parse to volume 1, not fall through to the volume-1 default.
The Lore Olympus failure mode: every spelled volume landed as volume 1 (so
Vol. One..Eleven all collapsed onto a single "volume 1" row).
"""
from utils import Series
import publisher


def parse_one(title: str, fmt: str = 'Physical'):
    """Run one Info row through the generic publisher parser, return the Book."""
    from utils import Info
    series = Series(None, title)
    info = {fmt: [Info(series.key, f'http://x/{title}', 'Seven Seas Entertainment',
                       'Seven Seas Entertainment', title, 0, fmt, '', None)]}
    books = publisher.parse(series, info, {})
    flat = [b for lst in books.values() for b in lst if b]
    assert len(flat) == 1, f'{title!r} -> {[b.volume for b in flat]}'
    return flat[0]


class TestWordNumberVolume:
    def test_volume_one(self):
        assert parse_one('Age Matters Volume One').volume == '1'

    def test_volume_eight(self):
        assert parse_one('Flight Volume Eight').volume == '8'

    def test_colon_volume_nine(self):
        assert parse_one('Lore Olympus: Volume Nine').volume == '9'

    def test_period_volume_four(self):
        assert parse_one('Boyfriends. Volume Four').volume == '4'

    def test_distinct_word_volumes_distinct_numbers(self):
        # the failure mode: these all collapsed to volume 1
        assert parse_one('Age Matters Volume One').volume == '1'
        assert parse_one('Age Matters Volume Two').volume == '2'


class TestDigitVolumeUnaffected:
    def test_vol_dot_number(self):
        assert parse_one('Solo Leveling, Vol. 1').volume == '1'

    def test_volume_number(self):
        assert parse_one('Some Series Volume 3').volume == '3'
