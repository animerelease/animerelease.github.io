"""Sentai Filmworks Shopify parsing (source/sentai.py).

Fixtures mirror the live products.json shape: UPC-prefixed handle, vendor
'Sentai', product_type 'Video', variant option1 = format, sku = catalog, tags
carrying edition/pre-order. The street date comes off the product page, so the
release-date regex is exercised against a page-HTML snippet.
"""
import datetime

import source.sentai as s
from utils import EPOCH


def product(**over):
    p = {
        'handle': '816726029245-my-mental-choices-blu-ray',
        'title': 'My Mental Choices Complete Collection',
        'vendor': 'Sentai',
        'product_type': 'Video',
        'tags': ['Blu-ray', 'Sub', 'Sentai Filmworks'],
        'variants': [{'option1': 'Blu-ray', 'sku': 'SFB-MMC110'}],
    }
    p.update(over)
    return p


def parse(**over):
    res = s.parse_product(product(**over))
    assert res is not None
    return res


class TestUpc:
    def test_upc_is_handle_prefix(self):
        _, inf = parse()
        assert inf.upc == '816726029245'

    def test_no_prefix_gives_blank_upc(self):
        _, inf = parse(handle='after-the-rain-complete-collection-blu-ray')
        assert inf.upc == ''

    def test_upc_from_handle_helper(self):
        assert s.upc_from_handle('816726028071-dangers-in-my-heart') == '816726028071'
        assert s.upc_from_handle('no-digits-here') == ''


class TestCoreFields:
    def test_catalog_region_source(self):
        _, inf = parse()
        assert inf.catalog == 'SFB-MMC110'
        assert inf.region == 'A'            # Sentai is NA / Region A
        assert inf.source == inf.publisher == s.NAME

    def test_format_from_option1(self):
        _, inf = parse(variants=[{'option1': 'DVD', 'sku': 'SFD-1'}])
        assert inf.format == 'DVD'

    def test_format_falls_back_to_tag(self):
        _, inf = parse(variants=[{'option1': 'Default Title', 'sku': 'X'}],
                       tags=['DVD', 'Sub'])
        assert inf.format == 'DVD'


class TestEditionAndFilter:
    def test_steelbook_from_title(self):
        _, inf = parse(title='The Dangers in My Heart Limited Edition SteelBook')
        assert inf.edition == 'SteelBook'

    def test_limited_from_tags(self):
        _, inf = parse(tags=['Blu-ray', 'Collector'])
        assert inf.edition == 'LE'

    def test_non_video_skipped(self):
        assert s.parse_product(product(product_type='Apparel')) is None

    def test_non_sentai_vendor_skipped(self):
        assert s.parse_product(product(vendor='Section23')) is None

    def test_unknown_format_skipped(self):
        assert s.parse_product(
            product(variants=[{'option1': 'Default Title', 'sku': 'X'}], tags=['Sub'])) is None


class TestPreorderAndDate:
    def test_is_preorder(self):
        assert s.is_preorder(['Pre-Order', 'Blu-ray'])
        assert s.is_preorder(['Pre-Flag'])
        assert not s.is_preorder(['Blu-ray', 'Sub'])

    def test_release_date_regex(self):
        from utils import extract_release_date
        snippet = '<strong>Release Date:</strong> <span class="releasedate">September 29, 2026</span>'
        m = s.RELEASE_DATE.search(snippet)
        assert m
        assert extract_release_date(m.group(1)) == datetime.date(2026, 9, 29)

    def test_parse_leaves_date_unresolved(self):
        # products.json has no date; it is enriched later from the product page
        _, inf = parse()
        assert inf.date == EPOCH
