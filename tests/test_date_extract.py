"""Prose/HTML release-date extraction (utils.extract_release_date).

Anime stores give the street date only in prose: MediaOCD's short_description
says "Expected in mid-August", AllTheAnime buries a full date in body_html. The
shared helper walks a precision ladder and infers the year for month-only text.
"""
import datetime

from utils import extract_release_date

TODAY = datetime.date(2026, 7, 17)


def d(text):
    return extract_release_date(text, TODAY)


class TestExplicitDates:
    def test_month_day_year(self):
        assert d('Releases August 12, 2026') == datetime.date(2026, 8, 12)

    def test_day_month_year(self):
        assert d('Coming 3rd August 2026') == datetime.date(2026, 8, 3)

    def test_month_year_is_first(self):
        assert d('Available October 2026') == datetime.date(2026, 10, 1)

    def test_html_is_stripped(self):
        assert d('<p><strong>Releases August 12, 2026</strong></p>') == datetime.date(2026, 8, 12)


class TestQualifiedMonths:
    def test_mid_month(self):
        assert d('<p><strong>Expected in mid-August</strong></p>') == datetime.date(2026, 8, 15)

    def test_early_month(self):
        assert d('Expected in early September') == datetime.date(2026, 9, 5)

    def test_late_month(self):
        assert d('late December') == datetime.date(2026, 12, 25)

    def test_year_rolls_forward_for_past_month(self):
        # January < July -> next occurrence is next year
        assert d('mid-January') == datetime.date(2027, 1, 15)

    def test_current_month_stays_this_year(self):
        assert d('in July') == datetime.date(2026, 7, 1)


class TestNoDate:
    def test_empty(self):
        assert d('') is None

    def test_none(self):
        assert extract_release_date(None, TODAY) is None

    def test_year_without_month_is_not_a_date(self):
        # "Year of Original Release: 1984" must not be read as a street date
        assert d('Year of Original Release: 1984 . Number of Discs: 4') is None
