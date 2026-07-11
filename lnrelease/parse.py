import importlib
import re
import warnings
from collections import Counter, defaultdict
from itertools import groupby
from operator import attrgetter
from pathlib import Path

import publisher
from scrape import INFO, SERIES
from utils import DIGITAL, FORMATS, PRIMARY, SECONDARY, SOURCES, Book, Info, Series, Table

# digital serialized chapters (e.g. Square Enix "... #001", "Beast Tamer #097")
# are not volume releases; keep them out of the calendar. Physical "#" issues
# (a few Dark Horse single issues) are legitimate and stay.
CHAPTER = re.compile(r'#\s*\d+')

PUBLISHERS = {}
for file in Path('lnrelease/publisher').glob('*.py'):
    module = importlib.import_module(f'publisher.{file.stem}')
    PUBLISHERS[module.NAME] = module

BOOKS = Path('books.csv')
ARTBOOKS = Path('artbooks.csv')


def main() -> None:
    series = {row.key: row for row in Table(SERIES, Series)}
    info = Table(INFO, Info)
    # publishers that produced at least one primary-source row this run. A
    # PRIMARY publisher's aggregator (SECONDARY) copies are normally dropped as
    # duplicates of its own scraper's rows -- but only when that scraper
    # actually ran. If it produced nothing (e.g. Kodansha/VIZ/TOKYOPOP, whose
    # only rows come from PRH/Crunchyroll), keep the aggregator copies instead
    # of dropping the publisher entirely.
    scraped_pubs = {i.publisher for i in info if i.source not in SECONDARY}
    links: defaultdict[str, list[Info]] = defaultdict(list)
    lst: list[Info] = []
    for i in info:
        links[i.link].append(i)
        if CHAPTER.search(i.title) and i.format in DIGITAL:
            continue  # digital serialized chapter, not a volume
        redundant = (i.source in SECONDARY and i.publisher in PRIMARY
                     and i.publisher in scraped_pubs)
        if not redundant:
            lst.append(i)
    lst.sort()
    # sort by source then title
    links = dict(sorted(links.items(), key=lambda x: (SOURCES[x[1][0].source], x[1][0].title)))
    BOOKS.unlink(missing_ok=True)
    ARTBOOKS.unlink(missing_ok=True)
    books = Table(BOOKS, Book)

    for key, group in groupby(lst, attrgetter('serieskey', 'publisher')):
        serieskey = key[0]
        serie = series[serieskey]
        pub = key[1]
        if pub in PUBLISHERS:
            module = PUBLISHERS[pub]
        else:
            module = publisher
            warnings.warn(f'Unknown publisher: {pub}; {serieskey}', RuntimeWarning)
        inf: defaultdict[str, list[Info]] = defaultdict(list)
        for i in group:
            inf[i.format].append(i)
        inf = dict(sorted(inf.items(), key=lambda x: FORMATS.get(x[0], 0)))
        for x in module.parse(serie, inf, links).values():
            books.update(x)

    for book in books:
        if serie := series.get(book.serieskey):
            # unresolved series default to the JP manga base rate
            book.origin = serie.origin or 'JP'
            book.category = serie.category or 'manga'

    # collapse the same edition appearing more than once: across series keys
    # (e.g. "Lore Olympus Graphic Novel" vs "Lore Olympus: Volume One", or a
    # title split under an aggregator and a publisher key) or under one key with
    # differing titles (a merged dup key). An ISBN + format identifies exactly
    # one edition, so keep a single row per (ISBN, format) -- on the key that
    # carries the most volumes (the consolidated series). Keying on format too
    # preserves distinct Digital vs eBook rows that legitimately share an ISBN.
    by_edition: defaultdict[tuple[str, str], list[Book]] = defaultdict(list)
    for book in books:
        if book.isbn:
            by_edition[(book.isbn, book.format)].append(book)
    keycount = Counter(book.serieskey for book in books)
    for dupes in by_edition.values():
        if len(dupes) > 1:
            canon = max(dupes, key=lambda b: (keycount[b.serieskey], -len(b.serieskey)))
            for b in dupes:
                if b is not canon:
                    books.discard(b)

    # art books go to their own file, same schema; the main dataset and the
    # release calendar (built downstream from books.csv) stay manga/comics only
    artbooks = Table(ARTBOOKS, Book)
    for book in list(books):
        if book.category == 'artbook':
            books.discard(book)
            artbooks.add(book)
    books.save()
    artbooks.save()


if __name__ == '__main__':
    main()
