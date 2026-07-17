"""AllTheAnime Shopify parsing (source/alltheanime.py).

Fixtures mirror the live products.json: the disc specs live in body_html
("Release Date: dd/mm/yyyy" UK-first, Region, Format), product_type is the
disc/edition type, vendor is the distributor, sku is the catalog. No UPC; Region
B by default.
"""
import datetime

import source.alltheanime as a

BODY = ('<div>Synopsis ...</div>'
        '<p>Release Date: 14/09/2026</p>'
        '<p>Region: B</p>'
        '<p>Format: Blu-Ray</p>'
        '<p>Number of discs: 2</p>')


def product(**over):
    p = {
        'handle': 'undead-unluck-part-2-blu-ray',
        'title': 'Undead Unluck Part 2 - Blu-ray',
        'vendor': 'Anime Limited',
        'product_type': 'Blu-ray',
        'body_html': BODY,
        'variants': [{'option1': 'Default Title', 'sku': 'ANI1207'}],
    }
    p.update(over)
    return p


def parse(**over):
    res = a.parse_product(product(**over))
    assert res is not None
    return res


class TestCoreFields:
    def test_catalog_vendor_no_upc(self):
        _, inf = parse()
        assert inf.catalog == 'ANI1207'
        assert inf.publisher == 'Anime Limited'
        assert inf.upc == ''                 # AllTheAnime exposes no barcode
        assert inf.source == a.NAME

    def test_uk_crunchyroll_vendor_kept(self):
        _, inf = parse(vendor='Crunchyroll', variants=[{'sku': 'UKCR0347'}])
        assert inf.publisher == 'Crunchyroll'
        assert inf.catalog == 'UKCR0347'


class TestBodyHtmlSpecs:
    def test_release_date_is_uk_day_first(self):
        _, inf = parse()
        assert inf.date == datetime.date(2026, 9, 14)   # 14/09, not 9 Apr

    def test_region_from_body(self):
        _, inf = parse()
        assert inf.region == 'B'

    def test_region_defaults_to_b(self):
        _, inf = parse(body_html='<p>Release Date: 14/09/2026</p><p>Format: Blu-ray</p>')
        assert inf.region == 'B'

    def test_format_normalized_from_body(self):
        _, inf = parse()
        assert inf.format == 'Blu-ray'       # "Blu-Ray" normalized

    def test_non_date_release_line_is_ignored(self):
        _, inf = parse(body_html='<p>Release Date: as soon as stock arrives</p>'
                                 '<p>Format: Blu-ray</p><p>Region: B</p>')
        assert str(inf.date) == '0001-01-01'


class TestFormatAndEdition:
    def test_4k_uhd(self):
        _, inf = parse(product_type='4K UHD',
                       body_html='<p>Format: 4K Ultra HD</p><p>Region: B</p>')
        assert inf.format == '4K UHD'

    def test_steelbook_edition_defaults_bluray(self):
        _, inf = parse(product_type='Steelbook',
                       title='Kaiju No. 8 Steelbook',
                       body_html='<p>Region: B</p>')  # no Format line
        assert inf.format == 'Blu-ray'
        assert inf.edition == 'SteelBook'

    def test_collectors_edition(self):
        _, inf = parse(product_type="Collector's Edition",
                       title="NARUTO Collector's Edition")
        assert inf.edition == 'LE'


class TestFiltering:
    def test_non_disc_product_skipped(self):
        assert a.parse_product(
            product(product_type='T-Shirt', title='Cool Tee',
                    body_html='<p>100% cotton</p>')) is None

    def test_normalize_format_helper(self):
        assert a.normalize_format('Blu-Ray') == 'Blu-ray'
        assert a.normalize_format('4K Ultra HD') == '4K UHD'
        assert a.normalize_format('DVD') == 'DVD'
        assert a.normalize_format('Soundtrack') == ''
