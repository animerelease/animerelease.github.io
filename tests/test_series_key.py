"""Series-key canonicalization for the anime disc model.

The series key is generated in Series.__post_init__ at scrape time. For anime it
must drop the trailing disc-format/edition token a store appends to a product
name, so a title's Blu-ray and DVD editions collapse to one series key, and it
must derive the release category (TV / movie / OVA) from title markers.
"""
from utils import Series, category_marker


def key(title: str) -> str:
    return Series(None, title).key


class TestDiscSuffixStripped:
    def test_bluray_suffix(self):
        assert key('Kekkaishi: The Complete Series - Blu-ray') == 'kekkaishithecompleteseries'

    def test_dvd_suffix(self):
        assert key('Kekkaishi: The Complete Series - DVD') == 'kekkaishithecompleteseries'

    def test_bluray_and_dvd_collapse(self):
        # the whole point: two disc editions of one title are one series
        assert key('Wicked City – Blu-ray') == key('Wicked City – DVD')

    def test_4k_uhd_paren_suffix(self):
        assert key('Akira (4K UHD)') == 'akira'

    def test_bare_title_unchanged(self):
        assert key('Cowboy Bebop') == 'cowboybebop'


class TestCategoryMarker:
    def test_the_movie_subtitle(self):
        assert category_marker('Adieu Galaxy Express 999: The Movie') == 'movie'

    def test_paren_movie(self):
        assert category_marker('Some Title (Movie)') == 'movie'

    def test_ova(self):
        assert category_marker('Kiss x Sis: The Complete OVA Series') == 'OVA'

    def test_ona(self):
        assert category_marker('Some Title ONA Collection') == 'ONA'

    def test_no_marker_is_blank(self):
        # a plain TV series has no marker; the TV default is applied at output
        assert category_marker('Vinland Saga Season 1 Complete Collection') == ''

    def test_movie_word_not_matched_outside_brackets(self):
        # a bare "movie" mid-title is too weak a signal to categorize on
        assert category_marker('The Movie Buff Diaries') == ''


class TestSeriesCategorySet:
    def test_series_picks_up_marker_category(self):
        s = Series(None, 'Adieu Galaxy Express 999: The Movie – Blu-ray')
        assert s.category == 'movie'
        assert s.title == 'Adieu Galaxy Express 999: The Movie'
