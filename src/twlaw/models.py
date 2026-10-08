"""Records returned by the query API."""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Article:
    """One article, carrying enough context to be cited on its own."""

    law_id: str
    law_name: str
    category: str
    seq: int
    article_no: str | None
    article_key: str | None
    content: str | None
    chapter_path: str | None
    # One field per heading level; None where the law has no such level.
    part: str | None        # 編
    chapter: str | None     # 章
    section: str | None     # 節
    subsection: str | None  # 款
    item: str | None        # 目
    repealed: bool
    # Whether the article's Law is abolished, joined in so a search hit shows it
    # without a second lookup.
    abolished: bool


class Articles:
    """One law's articles in order, indexed by the number they are cited by.

    ``articles[1]`` is 第 1 條 and ``articles["4-1"]`` is 第 4 條之一, the same
    keys :meth:`LawDB.get_article` takes. Positions cannot serve: 之一 articles
    sit between whole numbers, so the n-th article is often not 第 n 條.
    Iterating yields the articles in order; ``in`` tests for a number.
    """

    __slots__ = ("_list", "_by_key")

    def __init__(self, articles: Iterable[Article] = ()):
        self._list = list(articles)
        self._by_key = {a.article_key: a for a in self._list}

    @staticmethod
    def _key(number: int | str) -> str:
        return str(number).strip()

    def __getitem__(self, number: int | str) -> Article:
        try:
            return self._by_key[self._key(number)]
        except KeyError:
            raise KeyError(f"no article {number!r}") from None

    def get(self, number: int | str, default: Article | None = None) -> Article | None:
        return self._by_key.get(self._key(number), default)

    def __contains__(self, number: object) -> bool:
        return isinstance(number, (int, str)) and self._key(number) in self._by_key

    def __iter__(self) -> Iterator[Article]:
        return iter(self._list)

    def __len__(self) -> int:
        return len(self._list)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Articles) and self._list == other._list

    def __repr__(self) -> str:
        return f"Articles({len(self._list)} articles)"


@dataclass(frozen=True, slots=True)
class Law:
    """One law's metadata.

    ``articles`` is filled by :meth:`LawDB.get_law` and left empty by
    :meth:`LawDB.list_laws`, which returns metadata only.
    """

    id: str
    lang: str
    category: str
    name: str
    name_en: str | None
    level: str | None
    moj_category: str | None
    modified_date: str | None
    effective_date: str | None
    effective_note: str | None
    abandon_note: str | None
    abolished: bool
    foreword: str | None
    histories: str | None
    url: str | None
    update_date: str | None
    articles: Articles = field(default_factory=Articles)
