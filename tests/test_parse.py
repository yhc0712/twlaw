"""Parsing of MOJ's article lists into flat rows with explicit hierarchy."""

from twlaw.parse import article_key, iter_rows


def zh_dataset(articles, name="測試法", pcode="A0000001"):
    return {
        "UpdateDate": "2026/9/11 上午 12:00:00",
        "Laws": [
            {
                "LawName": name,
                "EngLawName": "Test Act",
                "LawLevel": "法律",
                "LawCategory": "行政＞財政部＞賦稅目",
                "LawModifiedDate": "20260911",
                "LawEffectiveDate": "99991231",
                "LawEffectiveNote": "",
                "LawAbandonNote": "",
                "LawForeword": "",
                "LawHistories": "",
                "LawURL": f"https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode={pcode}",
                "LawArticles": articles,
            }
        ],
    }


def en_dataset(articles, pcode="A0000001"):
    """English records prefix every field with Eng and omit several others."""
    return {
        "UpdateDate": "2026/9/11 上午 12:00:00",
        "Laws": [
            {
                "LawName": "測試法",
                "EngLawName": "Test Act",
                "LawLevel": "法律",
                "EngLawModifiedDate": "20260911",
                "EngLawAbandonNote": "",
                "EngLawForeword": "",
                "EngLawHistories": "",
                "EngLawURL": f"https://law.moj.gov.tw/Eng/LawClass/LawAll.aspx?pcode={pcode}",
                "EngLawArticles": articles,
            }
        ],
    }


def heading(text):
    return {"ArticleType": "C", "ArticleNo": "", "ArticleContent": text}


def article(no, content):
    return {"ArticleType": "A", "ArticleNo": no, "ArticleContent": content}


def only(dataset, category="law", lang="zh"):
    rows = list(iter_rows(dataset, category, lang))
    assert len(rows) == 1
    return rows[0]


class TestHierarchy:
    """Indentation is the only encoding of depth: 0=編 3=章 6=節 9=款 12=目."""

    def test_nested_headings_become_a_path(self):
        _, articles = only(zh_dataset([
            heading("   第 一 章 總則"),
            heading("      第 一 節 一般規定"),
            article("第 1 條", "內容一"),
        ]))
        assert articles[0]["chapter_path"] == "第 一 章 總則 / 第 一 節 一般規定"

    def test_deeper_heading_replaces_only_deeper_levels(self):
        _, articles = only(zh_dataset([
            heading("   第 一 章 總則"),
            heading("      第 一 節 甲"),
            article("第 1 條", "a"),
            heading("      第 二 節 乙"),
            article("第 2 條", "b"),
        ]))
        assert articles[0]["chapter_path"] == "第 一 章 總則 / 第 一 節 甲"
        assert articles[1]["chapter_path"] == "第 一 章 總則 / 第 二 節 乙"

    def test_shallower_heading_discards_deeper_levels(self):
        _, articles = only(zh_dataset([
            heading("   第 一 章 甲"),
            heading("      第 一 節 乙"),
            article("第 1 條", "a"),
            heading("   第 二 章 丙"),
            article("第 2 條", "b"),
        ]))
        assert articles[1]["chapter_path"] == "第 二 章 丙"

    def test_all_five_levels_nest(self):
        _, articles = only(zh_dataset([
            heading("第 一 編 編"),
            heading("   第 一 章 章"),
            heading("      第 一 節 節"),
            heading("         第 一 款 款"),
            heading("            第 一 目 目"),
            article("第 1 條", "x"),
        ]))
        assert articles[0]["chapter_path"] == "第 一 編 編 / 第 一 章 章 / 第 一 節 節 / 第 一 款 款 / 第 一 目 目"

    def test_articles_before_any_heading_have_empty_path(self):
        _, articles = only(zh_dataset([article("第 1 條", "x")]))
        assert articles[0]["chapter_path"] == ""

    def test_skipped_level_does_not_shift_the_path(self):
        """A 節 directly under a 編, with no 章 between, must not absorb the gap."""
        _, articles = only(zh_dataset([
            heading("第 一 編 編"),
            heading("      第 一 節 節"),
            article("第 1 條", "x"),
        ]))
        assert articles[0]["chapter_path"] == "第 一 編 編 / 第 一 節 節"

    def test_headings_are_not_emitted_as_articles(self):
        _, articles = only(zh_dataset([
            heading("   第 一 章 總則"),
            article("第 1 條", "x"),
        ]))
        assert len(articles) == 1
        assert articles[0]["article_no"] == "第 1 條"


class TestEnglishSchema:
    """English datasets use Eng-prefixed field names — a separate code path."""

    def test_english_records_are_parsed(self):
        law, articles = only(
            en_dataset([
                {"EngArticleType": "C", "EngArticleNo": "",
                 "EngArticleContent": "   Chapter I. General Provisions"},
                {"EngArticleType": "A", "EngArticleNo": "Article 1",
                 "EngArticleContent": "Text."},
            ]),
            lang="en",
        )
        assert law["id"] == "A0000001"
        assert len(articles) == 1
        assert articles[0]["article_no"] == "Article 1"
        assert articles[0]["chapter_path"] == "Chapter I. General Provisions"

    def test_english_uses_its_own_url_field_for_the_id(self):
        law, _ = only(en_dataset([], pcode="G0340003"), lang="en")
        assert law["id"] == "G0340003"

    def test_zh_field_names_are_not_read_in_en_mode(self):
        """A record carrying only zh fields yields no id, so it is skipped."""
        dataset = zh_dataset([article("第 1 條", "x")])
        assert list(iter_rows(dataset, "law", "en")) == []


class TestLawRows:
    def test_id_comes_from_the_pcode_in_the_url(self):
        law, _ = only(zh_dataset([], pcode="G0340003"))
        assert law["id"] == "G0340003"

    def test_records_without_a_pcode_are_skipped(self):
        dataset = zh_dataset([])
        dataset["Laws"][0]["LawURL"] = "https://law.moj.gov.tw/no-code-here"
        assert list(iter_rows(dataset, "law", "zh")) == []

    def test_update_date_is_carried_onto_every_law(self):
        law, _ = only(zh_dataset([]))
        assert law["update_date"] == "2026/9/11 上午 12:00:00"

    def test_seq_is_sequential_and_skips_headings(self):
        _, articles = only(zh_dataset([
            article("第 1 條", "a"),
            heading("   第 一 章 甲"),
            article("第 2 條", "b"),
        ]))
        assert [a["seq"] for a in articles] == [0, 1]


class TestArticleKey:
    """The citable number, extracted so callers never parse label strings."""

    def test_plain_number(self):
        assert article_key("第 1 條") == "1"

    def test_sub_article_keeps_its_suffix(self):
        assert article_key("第 4-1 條") == "4-1"

    def test_english_label(self):
        assert article_key("Article 4-1") == "4-1"

    def test_bare_number(self):
        assert article_key("1") == "1"

    def test_trailing_punctuation_is_ignored(self):
        assert article_key("Article 34-1.") == "34-1"

    def test_no_number_gives_empty_string(self):
        assert article_key("") == ""
        assert article_key("附表") == ""

    def test_multi_digit(self):
        assert article_key("第 218 條") == "218"

    def test_key_is_attached_to_parsed_articles(self):
        _, articles = only(zh_dataset([
            article("第 4 條", "a"),
            article("第 4-1 條", "b"),
        ]))
        assert [a["article_key"] for a in articles] == ["4", "4-1"]
