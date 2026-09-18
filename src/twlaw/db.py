"""Local SQLite store and query API."""

import sqlite3
from pathlib import Path

from .fetch import CATEGORIES, LANGS, fetch_dataset
from .parse import iter_rows

DEFAULT_PATH = Path.home() / ".twlaw" / "law.db"

# Bump whenever the table layout changes. A database built by an older version
# is discarded and rebuilt rather than migrated: it is a cache of an upstream
# dataset, so re-downloading is simpler and cheaper than writing migrations.
SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS laws (
    id             TEXT NOT NULL,
    lang           TEXT NOT NULL,
    category       TEXT NOT NULL,
    name           TEXT NOT NULL,
    name_en        TEXT,
    level          TEXT,
    moj_category   TEXT,
    modified_date  TEXT,
    effective_date TEXT,
    effective_note TEXT,
    abandon_note   TEXT,
    foreword       TEXT,
    histories      TEXT,
    url            TEXT,
    update_date    TEXT,
    PRIMARY KEY (id, lang)
);

CREATE TABLE IF NOT EXISTS articles (
    rowid        INTEGER PRIMARY KEY,
    law_id       TEXT NOT NULL,
    lang         TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    article_no   TEXT,
    article_key  TEXT,
    content      TEXT,
    chapter_path TEXT,
    UNIQUE (law_id, lang, seq)
);

CREATE INDEX IF NOT EXISTS idx_articles_key ON articles(law_id, lang, article_key);

CREATE INDEX IF NOT EXISTS idx_laws_name ON laws(name);
CREATE INDEX IF NOT EXISTS idx_laws_category ON laws(category, lang);

-- 'trigram' rather than the default tokenizer: unicode61 treats an unbroken
-- run of CJK as a single token, so searching 所得稅 would miss every article
-- where it sits mid-phrase (50 hits instead of ~1400). Trigram indexes
-- 3-character windows, which matches Chinese substrings correctly. Its
-- tradeoff is that queries shorter than 3 characters never match, so search()
-- falls back to LIKE for those.
-- content='articles' makes this an external-content index: FTS stores only the
-- index, not a second copy of the text (which cost ~180MB).
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    content,
    chapter_path,
    content = 'articles',
    content_rowid = 'rowid',
    tokenize = 'trigram'
);
"""

_FTS_MIN_QUERY = 3

_LAW_COLUMNS = (
    "id", "lang", "category", "name", "name_en", "level", "moj_category",
    "modified_date", "effective_date", "effective_note", "abandon_note",
    "foreword", "histories", "url", "update_date",
)


class LawDB:
    """Query interface over a local copy of the MOJ law database."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connect()

        if self._stored_version() not in (0, SCHEMA_VERSION):
            self._rebuild()
        self._conn.executescript(_SCHEMA)
        self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _stored_version(self) -> int:
        """0 for a database this version can still use as-is, else its version."""
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version:
            return version
        # Written before versioning existed; usable only if it already has the
        # current columns.
        columns = {r[1] for r in self._conn.execute("PRAGMA table_info(articles)")}
        return 0 if not columns or "article_key" in columns else -1

    def _connect(self) -> None:
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")

    def _rebuild(self) -> None:
        """Discard a database written by an incompatible version of twlaw.

        Drops the objects rather than deleting the file: on Windows the file
        cannot be unlinked while another process still has it open.
        """
        with self._conn:
            for kind, name in self._conn.execute(
                "SELECT type, name FROM sqlite_master"
                " WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"
            ).fetchall():
                self._conn.execute(f'DROP {kind} IF EXISTS "{name}"')

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def is_empty(self) -> bool:
        return self._conn.execute("SELECT COUNT(*) FROM laws").fetchone()[0] == 0

    def update_date(self, category: str = "law", lang: str = "zh") -> str | None:
        row = self._conn.execute(
            "SELECT update_date FROM laws WHERE category=? AND lang=? LIMIT 1",
            (category, lang),
        ).fetchone()
        return row[0] if row else None

    def refresh(self, categories=CATEGORIES, langs=LANGS) -> dict[tuple[str, str], int]:
        """Re-download the given datasets and replace their rows.

        Returns the number of laws stored per ``(category, lang)``.
        """
        counts = {}
        for category in categories:
            for lang in langs:
                dataset = fetch_dataset(category, lang)
                counts[(category, lang)] = self._replace(dataset, category, lang)
        # Replacing rows leaves the FTS index in many small segments; merging
        # them keeps the file from growing on every refresh.
        with self._conn:
            self._conn.execute("INSERT INTO articles_fts (articles_fts) VALUES ('optimize')")
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return counts

    def _replace(self, dataset: dict, category: str, lang: str) -> int:
        law_params = []
        article_params = []

        for law_row, article_rows in iter_rows(dataset, category, lang):
            law_params.append(tuple(law_row[c] for c in _LAW_COLUMNS))
            for a in article_rows:
                article_params.append(
                    (
                        a["law_id"], lang, a["seq"], a["article_no"],
                        a["article_key"], a["content"], a["chapter_path"],
                    )
                )

        placeholders = ",".join("?" * len(_LAW_COLUMNS))
        with self._conn:
            # The FTS index mirrors `articles` by rowid, so drop its entries for
            # the rows being replaced before those rows disappear.
            self._conn.execute(
                "INSERT INTO articles_fts (articles_fts, rowid, content, chapter_path)"
                " SELECT 'delete', a.rowid, a.content, a.chapter_path FROM articles a"
                "  JOIN laws l ON l.id = a.law_id AND l.lang = a.lang"
                " WHERE l.category = ? AND l.lang = ?",
                (category, lang),
            )
            self._conn.execute(
                "DELETE FROM articles WHERE lang = ? AND law_id IN"
                " (SELECT id FROM laws WHERE category = ? AND lang = ?)",
                (lang, category, lang),
            )
            self._conn.execute("DELETE FROM laws WHERE category=? AND lang=?", (category, lang))

            self._conn.executemany(f"INSERT INTO laws VALUES ({placeholders})", law_params)
            self._conn.executemany(
                "INSERT INTO articles"
                " (law_id, lang, seq, article_no, article_key, content, chapter_path)"
                " VALUES (?,?,?,?,?,?,?)",
                article_params,
            )
            self._conn.execute(
                "INSERT INTO articles_fts (rowid, content, chapter_path)"
                " SELECT a.rowid, a.content, a.chapter_path FROM articles a"
                "  JOIN laws l ON l.id = a.law_id AND l.lang = a.lang"
                " WHERE l.category = ? AND l.lang = ?",
                (category, lang),
            )
        return len(law_params)

    def _ensure_data(self) -> None:
        if self.is_empty:
            raise RuntimeError("Local database is empty; call refresh() first.")

    def list_laws(self, category: str | None = None, lang: str = "zh", name_like: str | None = None) -> list[dict]:
        sql = "SELECT * FROM laws WHERE lang=?"
        params: list = [lang]
        if category:
            sql += " AND category=?"
            params.append(category)
        if name_like:
            sql += " AND name LIKE ?"
            params.append(f"%{name_like}%")
        sql += " ORDER BY name"
        return [dict(r) for r in self._conn.execute(sql, params)]

    def get_law(self, law: str, lang: str = "zh") -> dict | None:
        """Return one law with its articles, each carrying its chapter path.

        ``law`` may be a law name (``"所得稅法"``) or a MOJ law code
        (``"G0340003"``). Names are matched exactly, never by prefix, because
        法規 names nest — 所得稅法 is a prefix of 所得稅法施行細則.
        """
        self._ensure_data()
        row = self._conn.execute(
            "SELECT * FROM laws WHERE lang=? AND (id=? OR name=? OR name_en=?)",
            (lang, law, law, law),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["articles"] = [
            dict(r)
            for r in self._conn.execute(
                "SELECT seq, article_no, article_key, content, chapter_path FROM articles"
                " WHERE law_id=? AND lang=? ORDER BY seq",
                (result["id"], lang),
            )
        ]
        return result

    def get_article(self, law: str, article: str | int, lang: str = "zh") -> dict | None:
        """Return one article by its number, or ``None`` if there is no such article.

        ``article`` is the number as it is cited: ``4`` or ``"4"`` for 第 4 條,
        ``"4-1"`` for 第 4 條之一. ``law`` accepts a name or a law code, as in
        :meth:`get_law`.
        """
        self._ensure_data()
        row = self._conn.execute(
            "SELECT a.seq, a.article_no, a.article_key, a.content, a.chapter_path,"
            "       l.id AS law_id, l.name AS law_name"
            "  FROM articles a"
            "  JOIN laws l ON l.id = a.law_id AND l.lang = a.lang"
            " WHERE a.lang = ? AND a.article_key = ?"
            "   AND (l.id = ? OR l.name = ? OR l.name_en = ?)",
            (lang, str(article).strip(), law, law, law),
        ).fetchone()
        return dict(row) if row else None

    def search(
        self,
        query: str,
        lang: str = "zh",
        category: str | None = None,
        limit: int = 50,
        include_repealed: bool = False,
    ) -> list[dict]:
        """Full-text search over article content.

        Returns article rows annotated with their law's id and name, best match
        first. ``chapter_path`` is searchable but weighted far below ``content``
        so that matching a chapter title alone does not outrank a real hit.
        Repealed articles (``（刪除）`` / "(Deleted)") are excluded by default.
        """
        self._ensure_data()
        query = query.strip()
        if not query:
            return []

        select = (
            "SELECT a.law_id, l.name AS law_name, l.category, a.seq,"
            "       a.article_no, a.article_key, a.content, a.chapter_path"
        )
        params: list = []

        if len(query) >= _FTS_MIN_QUERY:
            sql = (
                f"{select}"
                "  FROM articles_fts f"
                "  JOIN articles a ON a.rowid = f.rowid"
                "  JOIN laws l ON l.id = a.law_id AND l.lang = a.lang"
                " WHERE articles_fts MATCH ? AND a.lang = ?"
            )
            params += [f'"{query}"', lang]
            order = " ORDER BY bm25(articles_fts, 10.0, 1.0)"
        else:
            # Trigram FTS cannot match queries this short.
            sql = (
                f"{select}"
                "  FROM articles a"
                "  JOIN laws l ON l.id = a.law_id AND l.lang = a.lang"
                " WHERE a.lang = ? AND a.content LIKE ?"
            )
            params += [lang, f"%{query}%"]
            order = " ORDER BY a.law_id, a.seq"

        if category:
            sql += " AND l.category = ?"
            params.append(category)
        if not include_repealed:
            sql += " AND a.content NOT LIKE '%刪除%' AND a.content NOT LIKE '%(Deleted)%'"

        params.append(limit)
        return [dict(r) for r in self._conn.execute(sql + order + " LIMIT ?", params)]
