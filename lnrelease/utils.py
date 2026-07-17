import csv
import datetime
import re
import unicodedata
import warnings
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Self

import store

# spelled-out volume numbers (One..Twenty). Publishers ship the same series with
# either "Vol. 9" or "Volume Nine", and both must strip to the same series key,
# or the word form leaks in as loreolympusvolumenine / flightvolumeeight (which
# also splits every spelled volume into its own singleton series). WORD_NUMBERS
# maps the words back to ints for volume parsing (see publisher/__init__.py).
WORD_NUMBERS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7,
    'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13,
    'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18,
    'nineteen': 19, 'twenty': 20,
}
WORD_NUMBER = '|'.join(WORD_NUMBERS)  # alternation for embedding in patterns
# a volume value: a digit run (1, 1.5, 1-3) or a spelled number with a trailing
# word boundary so "Volume Oneshot" is not read as "Volume One"
_VOL_VALUE = rf'(?:\d[\d\-\.]*|(?:{WORD_NUMBER})\b)'

# disc-format / edition / language tokens that stores append to a product name
# ("… – Blu-ray", "(4K UHD)", "- Limited Edition", "(Japanese Language)"). The
# scraper knows the format/edition separately, so these are noise in the title.
_DISC = (r'blu[- ]?ray|dvd|4k(?:\s*ultra)?(?:\s*hd|\s*uhd)?|uhd'
         r'|blu[- ]?ray\s*[/+&]\s*dvd|combo(?:\s*pack)?'
         r'|steel\s*book|limited\s*edition|collector\'?s\s*edition|deluxe\s*edition')
_EXTRA = r'japanese\s*language|english\s*(?:dub(?:bed)?|language)|sub(?:title[ds]?)?|dub(?:bed)?|uncut|uncensored'
# TITLE: drop parenthetical/bracketed format-edition-language markers anywhere
# in an Info title, so the calendar shows a clean release name.
TITLE = re.compile(r'\s*[\(\[](?:' + _DISC + r'|' + _EXTRA + r')[\)\]]', flags=re.IGNORECASE)
# SERIES: additionally strip a trailing format/edition token (with or without a
# leading dash/colon/paren) so a title's Blu-ray and DVD editions collapse to
# the same series key.
SERIES = re.compile(r'\s*(?:[–—:-]\s*)?[\(\[]?(?:' + _DISC + r')[\)\]]?\s*$', flags=re.IGNORECASE)
NONWORD = re.compile(r'\W')
IA = re.compile(r'https?://web\.archive\.org/web/\d{14}/(?P<url>.+)')

# physical disc formats, in display/sort order (widest → narrowest)
DISC_FORMATS = ('4K UHD', 'Blu-ray', 'DVD')
FORMATS = {x: i for i, x in enumerate(DISC_FORMATS)}
# format string → Format enum member; keys are the canonical values the scraper
# emits plus a few common variants
FORMAT_ALIASES = {
    'blu-ray': 'BLU_RAY', 'bluray': 'BLU_RAY', 'blu ray': 'BLU_RAY',
    'dvd': 'DVD',
    '4k uhd': 'UHD', '4k ultra hd': 'UHD', 'uhd': 'UHD', '4k': 'UHD',
}

# release sources (the scraper sites), in precedence / sort order. MediaOCD is
# the keyless WooCommerce aggregator built this pass; Sentai Filmworks and
# AllTheAnime are the next-pass direct stores (SOURCES.md) and are pre-registered
# so their rows sort deterministically once they land.
PRIMARY = (
    'MediaOCD',
    'Sentai Filmworks',
    'AllTheAnime',
)
# fallback aggregators: their rows are dropped in parse.py when a primary source
# already carries the same distributor's release. Amazon is the planned NA
# fallback for the Crunchyroll disc gap (SOURCES.md).
SECONDARY = (
    'Amazon',
)
SOURCES = {x: i for i, x in enumerate(PRIMARY + SECONDARY)}

# placeholder date
EPOCH = datetime.date(1, 1, 1)

# origin = production country; category = anime release type (reader vocabulary,
# not disc format). Unresolved series default to JP/TV at output time.
ORIGINS = ('JP', 'US', 'other')
CATEGORIES = ('TV', 'movie', 'OVA', 'ONA', 'special')
# title markers that identify the release category. A parenthetical/bracketed
# "(Movie)"/"(OVA)", a ": The Movie" subtitle, or a bare OVA/ONA token is a
# strong signal; a bare "movie" word is not, so it is only read inside brackets.
MARKER = re.compile(
    r'[\(\[](?P<bracket>the movie|movie|ova|ona)[\)\]]'
    r'|:\s*(?P<sub>the movie)\b'
    r'|\b(?P<ova>ova)\b|\b(?P<ona>ona)\b',
    flags=re.IGNORECASE)


def category_marker(title: str) -> str:
    """The category a title's markers imply ('movie' / 'OVA' / 'ONA'), or ''."""
    if match := MARKER.search(title):
        token = (match.group('bracket') or match.group('sub') or '').lower()
        if match.group('ova') or token == 'ova':
            return 'OVA'
        if match.group('ona') or token == 'ona':
            return 'ONA'
        return 'movie'
    return ''


def clean_str(s: str) -> str:
    return NONWORD.sub('', unicodedata.normalize('NFKD', s)).lower()


def volume_lt(a: str, b: str) -> bool:
    try:
        af = float(a.split('-')[0])
        bf = float(b.split('-')[0])
        return af < bf
    except ValueError:
        return a < b


# --- release-date extraction from prose HTML -------------------------------
# Anime stores frequently give the street date only in prose, not a field:
# MediaOCD's short_description says "Expected in mid-August"; AllTheAnime buries
# "Released: 12 August 2026" in body_html. This shared helper is the single
# home for parsing those (SOURCES.md data-model note).
_MONTHS = {
    'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
    'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
    'august': 8, 'aug': 8, 'september': 9, 'sept': 9, 'sep': 9, 'october': 10,
    'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12,
}
_MONTH_RE = '|'.join(sorted(_MONTHS, key=len, reverse=True))  # longest-first
_TAG_RE = re.compile(r'<[^>]+>')
# "August 12, 2026" / "12 August 2026" / "Aug 12th 2026"
_DATE_MDY = re.compile(rf'\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})', re.I)
_DATE_DMY = re.compile(rf'\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_RE})\.?\s+(\d{{4}})', re.I)
# "August 2026" (day unknown -> the 1st)
_DATE_MONTH_YEAR = re.compile(rf'\b({_MONTH_RE})\.?\s+(\d{{4}})', re.I)
# "mid-August" / "early August" / "late August" (year inferred)
_DATE_QUALIFIED = re.compile(rf'\b(early|mid|late)[\s-]+({_MONTH_RE})\b', re.I)
_DATE_MONTH = re.compile(rf'\b({_MONTH_RE})\b', re.I)
_QUALIFIER_DAY = {'early': 5, 'mid': 15, 'late': 25}


def _next_month_date(month: int, day: int, today: datetime.date) -> datetime.date:
    """The next occurrence of (month, day) not before today's month."""
    year = today.year + 1 if month < today.month else today.year
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return datetime.date(year, month, 1)


def extract_release_date(text: str, today: datetime.date | None = None) -> datetime.date | None:
    """Best-effort release date from prose or HTML, or None if no month is found.

    Precision ladder: an explicit "Month D, YYYY" (either order) wins; then
    "Month YYYY" (day 1); then a qualifier + month ("mid-August" -> the 15th) or
    a bare month, with the year taken as the next occurrence from `today`.

    Intended for a targeted field (WooCommerce short_description, a Shopify
    release line) rather than a full synopsis, where a stray month word would
    be a false positive.
    """
    if not text:
        return None
    text = _TAG_RE.sub(' ', text)
    today = today or datetime.date.today()

    for pat, order in ((_DATE_MDY, 'mdy'), (_DATE_DMY, 'dmy')):
        if m := pat.search(text):
            if order == 'mdy':
                month, day, year = _MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
            else:
                day, month, year = int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3))
            try:
                return datetime.date(year, month, day)
            except ValueError:
                return None
    if m := _DATE_MONTH_YEAR.search(text):
        return datetime.date(int(m.group(2)), _MONTHS[m.group(1).lower()], 1)
    if m := _DATE_QUALIFIED.search(text):
        return _next_month_date(_MONTHS[m.group(2).lower()], _QUALIFIER_DAY[m.group(1).lower()], today)
    if m := _DATE_MONTH.search(text):
        return _next_month_date(_MONTHS[m.group(1).lower()], 1, today)
    return None


class Format(StrEnum):
    NONE = ''
    UHD = '🟥'          # 4K UHD
    BLU_RAY = '🔷'      # Blu-ray
    DVD = '⚪'          # DVD
    MULTI = '📀'        # a release spanning more than one disc format

    @classmethod
    def from_str(cls, s: str) -> Self:
        member = FORMAT_ALIASES.get((s or '').strip().lower())
        if member:
            return cls[member]
        warnings.warn(f'Unknown format: {s}', RuntimeWarning)
        return cls.NONE


@dataclass
class Key:
    key: str
    date: datetime.date

    @classmethod
    def from_db(cls, link: str, date: str) -> None:
        date = datetime.date.fromisoformat(date) if date else None
        return cls(link, date)

    def __eq__(self, other: Self) -> bool:
        return isinstance(other, self.__class__) and self.key == other.key

    def __lt__(self, other: Self) -> bool:
        return self.key < other.key

    def __hash__(self) -> int:
        return hash(self.key)

    def __iter__(self) -> Iterator[Self]:
        yield self.key
        yield self.date


@dataclass
class Series:
    key: str
    title: str
    origin: str = ''
    category: str = ''
    flag: str = ''

    def __post_init__(self) -> None:
        if not self.category:
            self.category = category_marker(self.title)
        self.title = SERIES.sub('', self.title).replace('’', "'").strip()
        self.key = self.key or clean_str(self.title)

    @classmethod
    def from_db(cls, key: str, title: str, origin: str = '',
                category: str = '', flag: str = '') -> Self:
        return cls(key, title, origin, category, flag)

    def __eq__(self, other: Self) -> bool:
        return isinstance(other, self.__class__) and self.key == other.key

    def __lt__(self, other: Self) -> bool:
        return self.key < other.key

    def __hash__(self) -> int:
        return hash(self.key)

    def __iter__(self) -> Iterator[Self]:
        yield self.key
        yield self.title
        yield self.origin
        yield self.category
        yield self.flag


@dataclass
class Info:
    serieskey: str
    link: str
    source: str
    publisher: str
    title: str
    index: int  # unreliable, 0 is unset
    format: str
    upc: str            # UPC/EAN barcode; nullable — MediaOCD/AllTheAnime omit it
    catalog: str        # distributor catalog number (ES459, SFB-MMC110, ANI1207)
    region: str         # disc region: A / B / A/B, or a market (US / UK)
    edition: str        # limited-edition variant flag: '' / LE / SteelBook
    date: datetime.date
    alts: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if match := IA.fullmatch(self.link):
            self.link = match.group('url')
        self.title = TITLE.sub('', self.title).replace('’', "'").strip()
        self.date = self.date or EPOCH

    @classmethod
    def from_db(cls, serieskey: str, link: str, source: str, publisher: str, title: str,
                index: str, format: str, upc: str, catalog: str, region: str,
                edition: str, date: str, *alts: str) -> Self:
        index = int(index)
        date = datetime.date.fromisoformat(date)
        alts = list(alts)
        return cls(serieskey, link, source, publisher, title, index, format,
                   upc, catalog, region, edition, date, alts)

    def __eq__(self, other: Self) -> bool:
        return (isinstance(other, self.__class__)
                and store.equal(self.link, other.link)
                and self.format == other.format)

    def __lt__(self, other: Self) -> bool:
        if self.serieskey != other.serieskey:
            return self.serieskey < other.serieskey
        elif self.publisher != other.publisher:
            return self.publisher < other.publisher
        elif self.source != other.source:
            return SOURCES[self.source] < SOURCES[other.source]
        elif self.format != other.format:
            return self.format < other.format
        elif self.date != other.date:
            return self.date < other.date
        elif self.index != other.index:
            return self.index < other.index
        return self.link < other.link

    def __hash__(self) -> int:
        return hash((store.hash_link(self.link), self.format))

    def __iter__(self) -> Iterator[Self]:
        yield self.serieskey
        yield self.link
        yield self.source
        yield self.publisher
        yield self.title
        yield self.index
        yield self.format
        yield self.upc
        yield self.catalog
        yield self.region
        yield self.edition
        yield self.date
        self.alts.sort()
        for alt in self.alts:
            yield alt


@dataclass
class Book:
    serieskey: str
    link: str
    publisher: str
    name: str
    volume: str
    format: str
    upc: str
    catalog: str
    region: str
    edition: str
    date: datetime.date
    origin: str = ''
    category: str = ''

    @classmethod
    def from_db(cls, serieskey: str, link: str, publisher: str, name: str,
                volume: str, format: str, upc: str, catalog: str, region: str,
                edition: str, date: str, origin: str = '', category: str = '') -> Self:
        date = datetime.date.fromisoformat(date)
        return cls(serieskey, link, publisher, name, volume, format,
                   upc, catalog, region, edition, date, origin, category)

    @classmethod
    def from_info(cls, serieskey: str, inf: 'Info', name: str, volume: str) -> Self:
        """Build a Book from a parsed Info row, carrying the disc-identity
        fields (upc/catalog/region/edition) through unchanged."""
        return cls(serieskey, inf.link, inf.publisher, name, volume, inf.format,
                   inf.upc, inf.catalog, inf.region, inf.edition, inf.date)

    def __eq__(self, other: Self) -> bool:
        return (isinstance(other, self.__class__)
                and self.serieskey == other.serieskey
                and self.publisher == other.publisher
                and self.name == other.name
                and self.volume == other.volume
                and self.format == other.format
                and self.date == other.date)

    def __lt__(self, other: Self) -> bool:
        if self.serieskey != other.serieskey:
            return self.serieskey < other.serieskey
        elif self.format != other.format:
            return self.format < other.format
        elif self.publisher != other.publisher:
            return self.publisher < other.publisher
        elif self.date != other.date:
            return self.date < other.date
        elif self.volume != other.volume:
            return volume_lt(self.volume, other.volume)
        return self.name < other.name

    def __hash__(self) -> int:
        return hash((self.serieskey,
                     self.publisher,
                     self.name,
                     self.volume,
                     self.format,
                     self.date))

    def __iter__(self) -> Iterator[Self]:
        yield self.serieskey
        yield self.link
        yield self.publisher
        yield self.name
        yield self.volume
        yield self.format
        yield self.upc
        yield self.catalog
        yield self.region
        yield self.edition
        yield self.date
        yield self.origin
        yield self.category


@dataclass
class Release:
    serieskey: str
    link: str
    publisher: str
    name: str
    volume: str
    format: Format
    upc: str
    catalog: str
    region: str
    edition: str
    date: datetime.date
    origin: str = ''
    category: str = ''

    def __eq__(self, other: Self) -> bool:
        return (isinstance(other, self.__class__)
                and self.publisher == other.publisher
                and clean_str(self.name) == clean_str(other.name)
                and self.volume == other.volume
                and self.edition == other.edition
                and self.date == other.date)

    def __lt__(self, other: Self) -> bool:
        if self.date != other.date:
            return self.date < other.date
        elif self.serieskey != other.serieskey:
            return self.serieskey < other.serieskey
        elif self.publisher != other.publisher:
            return self.publisher < other.publisher
        elif self.volume != other.volume:
            return volume_lt(self.volume, other.volume)
        return self.name < other.name

    def __hash__(self) -> int:
        return hash((self.publisher,
                     clean_str(self.name),
                     self.volume,
                     self.edition,
                     self.date))


class Table(set[Key | Info | Book | Series]):
    def __init__(self, file: Path, cls: type[Key | Info | Book | Series]) -> None:
        super().__init__()
        self.file = file
        self.cls = cls
        if file.is_file():
            with open(self.file, 'r', encoding='utf-8', newline='') as f:
                for line in csv.reader(f):
                    self.add(self.cls.from_db(*line))

    def save(self) -> None:
        with open(self.file, 'w', encoding='utf-8', newline='') as f:
            csv.writer(f).writerows(sorted(self))


def find_series(title: str, series: set[Series]) -> Series | None:
    s = clean_str(title)
    matches: list[Series] = []
    for serie in series:
        if s.startswith(serie.key):
            matches.append(serie)
    if matches:
        return max(matches, key=lambda x: len(x.title))
    return None
