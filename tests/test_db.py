"""Storage and query behaviour, against a database built from fixtures."""

import sqlite3

import pytest

from twlaw import SCHEMA_VERSION
from twlaw.db import LawDB

from test_parse import article, en_dataset, heading, zh_dataset


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A LawDB whose refresh() serves fixtures instead of hitting the network."""
    datasets = {
        ("law", "zh"): zh_dataset(
            [
                heading("   第 一 章 總則"),
                article("第 1 條", "所得稅分為綜合所得稅及營利事業所得稅。"),
                article("第 4 條", "下列各種所得，免納所得稅。"),
                article("第 4-1 條", "證券交易所得停止課徵所得稅。"),
                article("第 5 條", "（刪除）"),
            ],
            name="所得稅法",
            pcode="G0340003",
        ),
        ("order", "zh"): zh_dataset(
            [article("第 11 條", "本細則依所得稅法第一百二十一條規定訂定。")],
            name="所得稅法施行細則",
            pcode="G0340004",
        ),
        ("law", "en"): en_dataset(
            [
                {"EngArticleType": "A", "EngArticleNo": "Article 1",
                 "EngArticleContent": "Income tax is classified into two categories."},
            ],
            pcode="G0340003",
        ),
        ("order", "en"): {"UpdateDate": "2026/9/11", "Laws": []},
    }
    monkeypatch.setattr(
        "twlaw.db.fetch_dataset", lambda category, lang, **kw: datasets[(category, lang)]
    )
    database = LawDB(tmp_path / "t.db")
    database.refresh()
    yield database
    database.close()


class TestRefresh:
    def test_stores_every_dataset(self, db):
        assert len(db.list_laws(category="law")) == 1
        assert len(db.list_laws(category="order")) == 1
        assert len(db.list_laws(lang="en")) == 1

    def test_is_idempotent(self, db):
        before = len(db.get_law("所得稅法")["articles"])
        db.refresh()
        assert len(db.get_law("所得稅法")["articles"]) == before

    def test_reports_counts_per_dataset(self, db):
        assert db.refresh()[("law", "zh")] == 1

    def test_keeps_the_fts_index_consistent(self, db):
        db.refresh()
        articles = db._conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        indexed = db._conn.execute("SELECT COUNT(*) FROM articles_fts").fetchone()[0]
        assert indexed == articles
        db._conn.execute("INSERT INTO articles_fts(articles_fts) VALUES('integrity-check')")


class TestGetLaw:
    def test_by_name(self, db):
        assert db.get_law("所得稅法")["id"] == "G0340003"

    def test_by_code(self, db):
        assert db.get_law("G0340003")["name"] == "所得稅法"

    def test_by_english_name(self, db):
        assert db.get_law("Test Act", lang="en")["id"] == "G0340003"

    def test_name_match_is_exact_not_prefix(self, db):
        """所得稅法 is a prefix of 所得稅法施行細則; each must resolve to itself."""
        assert db.get_law("所得稅法")["name"] == "所得稅法"
        assert db.get_law("所得稅法施行細則")["name"] == "所得稅法施行細則"

    def test_partial_name_is_not_a_match(self, db):
        assert db.get_law("所得稅") is None

    def test_unknown_law_returns_none(self, db):
        assert db.get_law("查無此法") is None

    def test_articles_are_ordered_and_carry_context(self, db):
        articles = db.get_law("所得稅法")["articles"]
        assert [a["seq"] for a in articles] == [0, 1, 2, 3]
        assert articles[0]["chapter_path"] == "第 一 章 總則"

    def test_empty_database_is_reported_clearly(self, tmp_path):
        with LawDB(tmp_path / "empty.db") as empty:
            with pytest.raises(RuntimeError, match="refresh"):
                empty.get_law("所得稅法")


class TestGetArticle:
    def test_by_int(self, db):
        assert db.get_article("所得稅法", 1)["article_no"] == "第 1 條"

    def test_by_str(self, db):
        assert db.get_article("所得稅法", "1")["article_no"] == "第 1 條"

    def test_sub_article_is_distinct_from_its_parent(self, db):
        assert db.get_article("所得稅法", 4)["article_no"] == "第 4 條"
        assert db.get_article("所得稅法", "4-1")["article_no"] == "第 4-1 條"

    def test_accepts_a_law_code(self, db):
        assert db.get_article("G0340003", "4-1")["article_no"] == "第 4-1 條"

    def test_works_for_orders(self, db):
        assert db.get_article("所得稅法施行細則", 11)["article_no"] == "第 11 條"

    def test_includes_chapter_and_law_context(self, db):
        found = db.get_article("所得稅法", 1)
        assert found["chapter_path"] == "第 一 章 總則"
        assert found["law_name"] == "所得稅法"
        assert found["law_id"] == "G0340003"

    def test_missing_article_returns_none(self, db):
        assert db.get_article("所得稅法", 9999) is None

    def test_missing_law_returns_none(self, db):
        assert db.get_article("查無此法", 1) is None


class TestSearch:
    def test_finds_an_article_by_its_own_words(self, db):
        """Regression: the default CJK tokenizer could not match mid-phrase."""
        hits = db.search("綜合所得稅")
        assert any(h["article_no"] == "第 1 條" for h in hits)

    def test_substring_inside_a_longer_run_matches(self, db):
        assert db.search("所得稅") != []

    def test_repealed_articles_are_excluded_by_default(self, db):
        assert all("刪除" not in h["content"] for h in db.search("所得稅"))

    def test_repealed_articles_can_be_included(self, db):
        hits = db.search("刪除", include_repealed=True)
        assert any("刪除" in h["content"] for h in hits)

    def test_category_filter(self, db):
        assert all(h["category"] == "order" for h in db.search("所得稅法", category="order"))

    def test_language_filter(self, db):
        assert db.search("Income tax", lang="en") != []
        assert db.search("Income tax", lang="zh") == []

    def test_limit_is_respected(self, db):
        assert len(db.search("所得稅", limit=1)) <= 1

    def test_hits_are_citable_via_article_key(self, db):
        hit = db.search("綜合所得稅")[0]
        again = db.get_article(hit["law_name"], hit["article_key"])
        assert again["content"] == hit["content"]

    def test_short_query_falls_back_to_like(self, db):
        """Trigram FTS cannot match fewer than 3 characters."""
        assert db.search("稅") != []

    def test_blank_query_returns_nothing(self, db):
        assert db.search("   ") == []

    def test_empty_database_is_reported_clearly(self, tmp_path):
        with LawDB(tmp_path / "empty.db") as empty:
            with pytest.raises(RuntimeError, match="refresh"):
                empty.search("所得稅")


class TestListLaws:
    def test_name_like_is_a_substring_match(self, db):
        names = {l["name"] for l in db.list_laws(name_like="所得稅")}
        assert names == {"所得稅法", "所得稅法施行細則"}

    def test_category_filter(self, db):
        assert [l["name"] for l in db.list_laws(category="order")] == ["所得稅法施行細則"]

    def test_excludes_other_languages(self, db):
        assert all(l["lang"] == "zh" for l in db.list_laws())


class TestSchemaVersion:
    def test_new_database_is_stamped(self, tmp_path):
        path = tmp_path / "v.db"
        with LawDB(path):
            pass
        assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

    def test_incompatible_database_is_discarded(self, tmp_path, db):
        """A future version's file must be rebuilt, not crash on open."""
        path = tmp_path / "t.db"
        db.close()
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA user_version = 999")
        conn.commit()
        conn.close()

        with LawDB(path) as rebuilt:
            assert rebuilt.is_empty
            assert sqlite3.connect(path).execute(
                "PRAGMA user_version"
            ).fetchone()[0] == SCHEMA_VERSION

    def test_prehistoric_database_without_the_key_column_is_discarded(self, tmp_path):
        path = tmp_path / "old.db"
        conn = sqlite3.connect(path)
        conn.executescript(
            "CREATE TABLE articles (law_id TEXT, lang TEXT, seq INT, content TEXT);"
            "INSERT INTO articles VALUES ('X','zh',0,'stale');"
        )
        conn.commit()
        conn.close()

        with LawDB(path) as rebuilt:
            columns = {r[1] for r in rebuilt._conn.execute("PRAGMA table_info(articles)")}
            assert "article_key" in columns
            assert rebuilt._conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 0

    def test_a_current_database_is_left_alone(self, db):
        db.refresh()
        assert not db.is_empty
        assert db.get_law("所得稅法") is not None
