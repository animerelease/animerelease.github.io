"""CSV column-contract round-trips for the anime data model.

The pipeline persists Info/Book by writing list(iter(obj)) as a CSV row and
reads them back with from_db(*row). The new disc fields (upc, catalog, region,
edition) must survive that trip in order, or info.csv/books.csv silently
corrupt. These pin the column layout.
"""
import datetime

from utils import Book, Info

DATE = datetime.date(2026, 8, 15)


def row(obj):
    # mirror Table.save/load: iterate to a CSV row, stringify like csv does
    return [str(x) for x in obj]


class TestInfoRoundTrip:
    def make(self):
        return Info('kekkaishi', 'https://mediaocd.com/product/kekkaishi/', 'MediaOCD',
                    'Discotek', 'Kekkaishi', 0, 'Blu-ray', '', 'ES500', 'A', 'SteelBook', DATE)

    def test_columns_in_order(self):
        assert row(self.make()) == [
            'kekkaishi', 'https://mediaocd.com/product/kekkaishi/', 'MediaOCD',
            'Discotek', 'Kekkaishi', '0', 'Blu-ray', '', 'ES500', 'A', 'SteelBook',
            '2026-08-15']

    def test_from_db_reconstructs(self):
        inf = self.make()
        back = Info.from_db(*row(inf))
        assert back.catalog == 'ES500'
        assert back.region == 'A'
        assert back.edition == 'SteelBook'
        assert back.upc == ''
        assert back.date == DATE
        assert back.format == 'Blu-ray'

    def test_upc_slot_carries_upc_when_present(self):
        inf = Info('s', 'l', 'MediaOCD', 'Sentai', 't', 0, 'DVD',
                   '816726029245', 'SFB-1', 'A', '', DATE)
        assert row(inf)[7] == '816726029245'
        assert Info.from_db(*row(inf)).upc == '816726029245'


class TestBookRoundTrip:
    def make(self):
        return Book('kekkaishi', 'https://mediaocd.com/product/kekkaishi/', 'Discotek',
                    'Kekkaishi', '1', 'Blu-ray', '', 'ES500', 'A', '', DATE, 'JP', 'TV')

    def test_columns_in_order(self):
        assert row(self.make()) == [
            'kekkaishi', 'https://mediaocd.com/product/kekkaishi/', 'Discotek',
            'Kekkaishi', '1', 'Blu-ray', '', 'ES500', 'A', '', '2026-08-15', 'JP', 'TV']

    def test_from_db_reconstructs(self):
        book = Book.from_db(*row(self.make()))
        assert book.catalog == 'ES500'
        assert book.region == 'A'
        assert book.origin == 'JP'
        assert book.category == 'TV'
        assert book.date == DATE

    def test_from_info_carries_disc_fields(self):
        inf = Info('s', 'l', 'MediaOCD', 'Sentai', 'Show', 0, 'DVD',
                   '816726029245', 'SFB-1', 'B', 'LE', DATE)
        book = Book.from_info('s', inf, 'Show', '1')
        assert (book.upc, book.catalog, book.region, book.edition) == \
            ('816726029245', 'SFB-1', 'B', 'LE')
        assert book.format == 'DVD'
