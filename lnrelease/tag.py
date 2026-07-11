import csv
import re
import warnings
from collections import defaultdict
from pathlib import Path

from scrape import INFO, SERIES
from utils import CATEGORIES, ORIGINS, Info, Series, Table

# manual overrides: key,origin,category (either may be blank); wins over heuristics
OVERRIDES = Path('origins.csv')

# publishers whose entire manga catalogue is licensed from Japan
JP_PUBLISHERS = {
    'Denpa',
    'J-Novel Club',
    'Kodansha',
    'One Peace Books',
    'Square Enix',
    'Udon Entertainment',
    'VIZ Media',
}
# publisher-level origin/category signals. Only for imprints with a single
# consistent origin. WEBTOON Unscrolled is deliberately absent: it is a mixed
# imprint (Korean manhwa like Tower of God AND western webtoons like Cursed
# Princess Club), so origin must be resolved per title (origins.csv), never
# defaulted to one country -- a blanket 'other'/'webtoon' here is what mistagged
# every Korean WEBTOON title.
PUB_TAGS = {
    'Ize Press': ('KR', 'manhwa'),
}
ARTBOOK = re.compile(r'\bart ?(?:book|works)\b|\bthe art of\b|\billustrations?\b|\bsketchbook\b',
                     flags=re.IGNORECASE)
# American-made comics published by otherwise-Japanese-catalogue houses (mostly
# Udon's game tie-ins) default to JP/manga without this. These franchises are
# unambiguously Western; note Mega Man (Ariga), Persona and Blue Archive are
# genuinely JP/mixed and are deliberately NOT matched -- curate those in origins.csv.
WESTERN = re.compile(r'\bstreet fighter\b|\bdarkstalkers\b|\bfinal fight\b'
                     r'|\bdragon\'?s crown\b|\bwakfu\b', flags=re.IGNORECASE)


def load_overrides() -> dict[str, tuple[str, str]]:
    overrides = {}
    if OVERRIDES.is_file():
        with open(OVERRIDES, 'r', encoding='utf-8', newline='') as f:
            for row in csv.reader(f):
                key, origin, category = row
                if origin and origin not in ORIGINS:
                    warnings.warn(f'Unknown origin override: {row}', RuntimeWarning)
                elif category and category not in CATEGORIES:
                    warnings.warn(f'Unknown category override: {row}', RuntimeWarning)
                else:
                    overrides[key] = (origin, category)
    return overrides


def tag(series: Table, info: Table, overrides: dict[str, tuple[str, str]]) -> None:
    publishers: defaultdict[str, set[str]] = defaultdict(set)
    for i in info:
        publishers[i.serieskey].add(i.publisher)

    flagged = 0
    for s in series:
        pubs = publishers.get(s.key, set())
        for publisher in pubs:
            if signal := PUB_TAGS.get(publisher):
                s.origin = s.origin or signal[0]
                s.category = s.category or signal[1]
        # Western game tie-ins from the mixed houses: override the JP default
        # (origin), tag as comic where a category isn't already set (keeps
        # existing artbook/anthology). Gated on publisher so a JP-licensed title
        # sharing a franchise name elsewhere isn't caught.
        if WESTERN.search(s.title) and pubs & {'Udon Entertainment', 'Ablaze'}:
            s.origin = 'other'
            s.category = s.category or 'comic'
        if not s.origin and pubs and pubs <= JP_PUBLISHERS:
            s.origin = 'JP'
        if not s.category and ARTBOOK.search(s.title):
            s.category = 'artbook'

        if override := overrides.get(s.key):
            origin, category = override
            s.origin = origin or s.origin
            s.category = category or s.category

        # unresolved origins stay empty (so future scrape signals can land)
        # and are flagged for manual curation; the JP/manga base-rate default
        # is applied at output time in parse.py/pages.py
        s.flag = '' if s.origin else 'review'
        flagged += bool(s.flag)

    print(f'tag: {len(series)} series tagged, {flagged} flagged for review, '
          f'{len(overrides)} overrides', flush=True)


def main() -> None:
    series = Table(SERIES, Series)
    info = Table(INFO, Info)
    tag(series, info, load_overrides())
    series.save()


if __name__ == '__main__':
    main()
