"""Cross-store edition merge (parse.merge_editions).

The same physical release listed by two stores must collapse to one row that
keeps a real date and a real UPC; a UK/Region-B edition must stay separate from
its NA counterpart; a limited edition must stay separate from the standard one.
"""
import datetime

from parse import merge_editions
from utils import EPOCH, Book, Table

DATE = datetime.date(2026, 9, 29)


def book(name, *, link='http://x', pub='P', fmt='Blu-ray', upc='', catalog='',
         region='A', edition='', date=EPOCH):
    return Book('k' + name.replace(' ', ''), link, pub, name, '1', fmt,
                upc, catalog, region, edition, date)


def table(tmp_path, books):
    t = Table(tmp_path / 'books.csv', Book)
    for b in books:
        t.add(b)
    merge_editions(t)
    return list(t)


class TestCrossStoreMerge:
    def test_merge_by_title_enriches_upc_and_date(self, tmp_path):
        # MediaOCD (no UPC, no date) + Sentai (UPC, real date) -> one row w/ both
        mocd = book('Akiba Maid War', link='http://mediaocd', pub='Discotek', catalog='ES1')
        sentai = book('Akiba Maid War', link='http://sentai', pub='Sentai Filmworks',
                      upc='816726020662', catalog='SFBAMW100', date=DATE)
        rows = table(tmp_path, [mocd, sentai])
        assert len(rows) == 1
        assert rows[0].upc == '816726020662'
        assert rows[0].date == DATE

    def test_merge_by_catalog_when_titles_differ(self, tmp_path):
        a = book('After the Rain: Complete Collection', link='http://mediaocd', catalog='SFBATR100')
        b = book('After the Rain Complete Collection', link='http://sentai',
                 catalog='SFB-ATR100', upc='816726000001')
        rows = table(tmp_path, [a, b])
        assert len(rows) == 1
        assert rows[0].upc == '816726000001'

    def test_merge_by_shared_upc(self, tmp_path):
        a = book('Title One', link='http://a', upc='811111111111')
        b = book('Title Two Different Name', link='http://b', upc='811111111111', date=DATE)
        rows = table(tmp_path, [a, b])
        assert len(rows) == 1
        assert rows[0].date == DATE


class TestMarketSeparation:
    def test_na_and_uk_stay_separate(self, tmp_path):
        na = book('Undead Unluck Part 2', region='A', pub='Sentai Filmworks', upc='81672600002')
        uk = book('Undead Unluck Part 2', region='B', pub='Anime Limited',
                  catalog='ANI1207', date=DATE)
        rows = table(tmp_path, [na, uk])
        assert len(rows) == 2

    def test_region_free_is_its_own_bucket(self, tmp_path):
        na = book('Some Show', region='A', upc='811111111112')
        free = book('Some Show', region='A/B', catalog='UKX1')
        rows = table(tmp_path, [na, free])
        assert len(rows) == 2


class TestEditionSeparation:
    def test_limited_and_standard_stay_separate(self, tmp_path):
        std = book('Kaiju No 8', edition='', upc='811111111113')
        le = book('Kaiju No 8', edition='SteelBook', upc='811111111114')
        rows = table(tmp_path, [std, le])
        assert len(rows) == 2


class TestCanonicalChoice:
    def test_row_with_date_and_upc_wins(self, tmp_path):
        bare = book('Show', link='http://bare', catalog='C1')
        best = book('Show', link='http://best', upc='811111111115', date=DATE, catalog='C1')
        [row] = table(tmp_path, [bare, best])
        assert row.link == 'http://best'
