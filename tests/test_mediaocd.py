"""MediaOCD WooCommerce Store API parsing (source/mediaocd.py).

Exercises parse_product against synthetic product dicts shaped like the live
feed (see SOURCES.md): format from the disc category, region from the
description prose, edition from the name, catalog from sku (never a UPC), and
the Anime-category filter.
"""
import datetime

import source.mediaocd as m
from utils import EPOCH


def product(**over):
    p = {
        'id': 1,
        'name': 'Kekkaishi: The Complete Series &#8211; Blu-ray',
        'permalink': 'https://mediaocd.com/product/kekkaishi/',
        'sku': 'ES500',
        'short_description': '<p><strong>Expected in mid-August</strong></p>',
        'description': '<p>Japanese Language with English Subtitles • Region A</p>',
        'categories': [{'slug': 'anime', 'name': 'Anime'},
                       {'slug': 'bluray', 'name': 'Blu-ray'}],
        'brands': [{'slug': 'discotek', 'name': 'Discotek'}],
    }
    p.update(over)
    return p


def parse(**over):
    res = m.parse_product(product(**over))
    assert res is not None
    return res  # (Series, Info)


class TestCoreFields:
    def test_catalog_is_sku_and_upc_blank(self):
        _, inf = parse()
        assert inf.catalog == 'ES500'
        assert inf.upc == ''  # MediaOCD exposes no barcode

    def test_publisher_is_distributor(self):
        _, inf = parse()
        assert inf.publisher == 'Discotek'
        assert inf.source == m.NAME

    def test_title_cleaned_of_format_suffix_and_entities(self):
        _, inf = parse()
        assert inf.title == 'Kekkaishi: The Complete Series'

    def test_link(self):
        _, inf = parse()
        assert inf.link == 'https://mediaocd.com/product/kekkaishi/'


class TestFormat:
    def test_bluray_category(self):
        _, inf = parse()
        assert inf.format == 'Blu-ray'

    def test_dvd_category(self):
        _, inf = parse(categories=[{'slug': 'anime'}, {'slug': 'dvd'}])
        assert inf.format == 'DVD'

    def test_4k_beats_bluray(self):
        _, inf = parse(categories=[{'slug': 'anime'}, {'slug': 'bluray'}, {'slug': '4k-uhd'}])
        assert inf.format == '4K UHD'

    def test_format_falls_back_to_name(self):
        _, inf = parse(name='Some Show - DVD', categories=[{'slug': 'anime'}])
        assert inf.format == 'DVD'


class TestRegionEditionDate:
    def test_region_from_description(self):
        _, inf = parse()
        assert inf.region == 'A'

    def test_region_ab(self):
        _, inf = parse(description='All regions. Region A/B disc.')
        assert inf.region == 'A/B'

    def test_no_region(self):
        _, inf = parse(description='<p>No region line here.</p>')
        assert inf.region == ''

    def test_edition_steelbook(self):
        _, inf = parse(name='Akira SteelBook - Blu-ray')
        assert inf.edition == 'SteelBook'

    def test_edition_limited(self):
        _, inf = parse(name='Akira Limited Edition - Blu-ray')
        assert inf.edition == 'LE'

    def test_no_edition(self):
        _, inf = parse()
        assert inf.edition == ''

    def test_date_from_short_description(self):
        _, inf = parse()
        assert inf.date == datetime.date(2026, 8, 15)

    def test_undated_falls_to_epoch(self):
        _, inf = parse(short_description='<p>In stock now.</p>')
        assert inf.date == EPOCH


class TestFiltering:
    def test_non_anime_skipped(self):
        # a Live Action / Books product (no anime category) is dropped
        assert m.parse_product(product(categories=[{'slug': 'live-action'}])) is None

    def test_unknown_format_skipped(self):
        assert m.parse_product(product(name='Mystery', categories=[{'slug': 'anime'}])) is None

    def test_series_category_marker(self):
        series, _ = parse(name='Akira: The Movie - Blu-ray',
                          short_description='', description='Region A')
        assert series.category == 'movie'
