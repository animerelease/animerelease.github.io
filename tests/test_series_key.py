"""Scraper-side series-key canonicalization (AUDIT task 5c).

The series key is generated in Series.__post_init__ at scrape time, so a key
that leaks a volume marker is recreated on every full re-scrape -- the in-data
merge of loreolympusvolumeN was only a migration, not a fix. The SERIES strip
must drop volume markers whether the volume is a digit ("Vol. 1") or a spelled
word ("Volume One"), so "Lore Olympus: Volume Nine" and "Lore Olympus" collapse
to one key.
"""
from utils import Series


def key(title: str) -> str:
    return Series(None, title).key


class TestDigitVolumesStripped:
    """Baseline: the digit case already worked; guard against regressing it."""

    def test_vol_dot_number(self):
        assert key('Solo Leveling, Vol. 1') == 'sololeveling'

    def test_volume_number(self):
        assert key('Some Series Volume 3') == 'someseries'

    def test_bare_series(self):
        assert key('Lore Olympus') == 'loreolympus'


class TestWordNumberVolumesStripped:
    """The bug: spelled-out volume numbers leaked into the key."""

    def test_lore_olympus_word_volume(self):
        assert key('Lore Olympus: Volume Nine') == 'loreolympus'
        assert key('Lore Olympus: Volume Ten') == 'loreolympus'

    def test_viral_hit_word_volume(self):
        assert key('Viral Hit: Volume One') == 'viralhit'

    def test_flight_word_volume(self):
        assert key('Flight Volume Eight') == 'flight'

    def test_age_matters_all_collapse(self):
        assert key('Age Matters Volume One') == 'agematters'
        assert key('Age Matters Volume Two') == 'agematters'
        assert key('Age Matters Volume One') == key('Age Matters Volume Two')

    def test_boyfriends_period_word_volume(self):
        assert key('Boyfriends. Volume Four') == 'boyfriends'

    def test_word_and_digit_collapse_together(self):
        # a series shipping some volumes numbered, some spelled, is one series
        assert key('Lore Olympus: Volume Nine') == key('Lore Olympus Volume 9')


class TestWordNumberFalsePositives:
    """Only strip a spelled number that is actually the volume token."""

    def test_word_in_title_not_stripped(self):
        # "One" as a title word, not a volume marker, must survive
        assert key('One Piece') == 'onepiece'
        assert key('Chapter One') == 'chapterone'

    def test_oneshot_boundary(self):
        # "Volume Oneshot" is not "Volume One" + "shot"
        assert key('Weird Volume Oneshot') == 'weirdvolumeoneshot'

    def test_numeric_part_subtitle_unaffected(self):
        # a numeric volume with a spelled "Part" subtitle keeps prior behaviour:
        # the numeric volume is stripped, the Part subtitle is not treated as
        # the volume (regression guard, matches pre-fix output)
        assert key('Black Hammer Volume 7: Reborn Part Three') == 'blackhammerrebornpartthree'
