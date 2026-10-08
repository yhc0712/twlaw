"""Normalize MOJ records into flat law/article rows.

MOJ interleaves structural headings and real articles in one article list:
``ArticleType == "C"`` rows are headings whose leading indentation encodes depth
(0=編, 3=章, 6=節, 9=款, 12=目), while ``ArticleType == "A"`` rows are articles
carrying no hierarchy of their own. Each article's position in the hierarchy is
therefore implicit, and is resolved here by walking the list and tracking the
heading stack.

The English datasets use the same layout but prefix every field name with
``Eng`` and omit the category/effective-date fields, so field access goes
through a per-language field map.
"""

import re

_PCODE_RE = re.compile(r"pcode=([A-Za-z0-9]+)", re.IGNORECASE)
_INDENT_RE = re.compile(r"^(\s*)")
_INDENT_UNIT = 3

# Heading depth -> Article field. Depth agrees with the 編/章/節/款/目 marker in
# every Chinese heading, and also covers English and unnumbered headings.
LEVELS = ("part", "chapter", "section", "subsection", "item")

_WHITESPACE_RE = re.compile(r"\s+")
_ZH_NUMERALS = "一二三四五六七八九十百千零〇○"
# "第 十一 章之一　標題" -> 第, 十一, 章, 之一, 標題. A doubled 第 occurs in the data.
_ZH_HEADING_RE = re.compile(
    rf"^第\s*(?:第\s*)?([{_ZH_NUMERALS}\s]+?)\s*([編章節款目])\s*(之\s*[{_ZH_NUMERALS}]+)?\s*(.*)$"
)

# "第 4-1 條" / "Article 4-1" -> "4-1". Both languages also use a bare number
# for a handful of appendix-style entries.
_ARTICLE_NO_RE = re.compile(r"(\d+(?:-\d+)?)")


def article_key(article_no: str) -> str:
    """Return the citable number in an article label, e.g. ``第 4-1 條`` -> ``4-1``."""
    match = _ARTICLE_NO_RE.search(article_no or "")
    return match.group(1) if match else ""


# A repealed article keeps its number but its whole body becomes a marker,
# written inconsistently: （刪除）, （本條刪除）, (Deleted), (deleted)., (Repealed.),
# 〔Deleted〕 and so on. Strip the brackets and punctuation and compare what is
# left, so that articles which merely mention 刪除 or "deleted" are kept.
_REPEALED_MARKERS = {"刪除", "本條刪除", "deleted", "delete", "deletion", "delet", "repealed"}
_MARKER_NOISE_RE = re.compile(r"[\s()（）\[\]〔〕【】.。．、]+")


def clean_heading(text: str) -> str:
    """Tidy a heading: ``第 四 章  稽徵程序`` -> ``第四章 稽徵程序``.

    MOJ spaces out the characters of the marker and separates it from the title
    with any mix of ASCII and full-width spaces. Headings without a 第…章 marker
    (English, or 壹/甲-numbered ones) only have their whitespace collapsed.
    """
    text = _WHITESPACE_RE.sub(" ", text).strip()
    match = _ZH_HEADING_RE.match(text)
    if not match:
        return text
    number, unit, sub, title = match.groups()
    marker = "第" + number.replace(" ", "") + unit + (sub or "").replace(" ", "")
    return f"{marker} {title}" if title else marker


def is_repealed(content: str) -> bool:
    """Whether an article's body is only a repeal marker such as ``（刪除）``."""
    return _MARKER_NOISE_RE.sub("", content or "").lower() in _REPEALED_MARKERS


# The two language variants name the same fields differently.
_FIELDS = {
    "zh": {
        "url": "LawURL",
        "modified_date": "LawModifiedDate",
        "abandon_note": "LawAbandonNote",
        "foreword": "LawForeword",
        "histories": "LawHistories",
        "articles": "LawArticles",
        "article_type": "ArticleType",
        "article_no": "ArticleNo",
        "article_content": "ArticleContent",
    },
    "en": {
        "url": "EngLawURL",
        "modified_date": "EngLawModifiedDate",
        "abandon_note": "EngLawAbandonNote",
        "foreword": "EngLawForeword",
        "histories": "EngLawHistories",
        "articles": "EngLawArticles",
        "article_type": "EngArticleType",
        "article_no": "EngArticleNo",
        "article_content": "EngArticleContent",
    },
}


# Some articles type the bopomofo ㄧ (U+3127) where the numeral 一 (U+4E00) is
# meant: 二分之ㄧ, 第ㄧ項. Every occurrence in the data is this typo, so all are
# replaced; otherwise searching for 一 would miss those articles. mojLawSplit
# (https://github.com/kong0107/mojLawSplit) applies the same conversion.
_TYPO_TABLE = str.maketrans({"ㄧ": "一"})


def _fix_typos(text: str) -> str:
    return text.translate(_TYPO_TABLE)


def _pcode(law: dict, url_field: str) -> str | None:
    match = _PCODE_RE.search(law.get(url_field, "") or "")
    return match.group(1) if match else None


def _heading_depth(content: str) -> int:
    return len(_INDENT_RE.match(content).group(1)) // _INDENT_UNIT


def iter_rows(dataset: dict, category: str, lang: str):
    """Yield ``(law_row, article_rows)`` pairs for one fetched dataset."""
    update_date = dataset.get("UpdateDate", "")
    f = _FIELDS[lang]

    for law in dataset.get("Laws", []):
        law_id = _pcode(law, f["url"])
        if law_id is None:
            continue

        law_row = {
            "id": law_id,
            "lang": lang,
            "category": category,
            "name": law.get("LawName", ""),
            "name_en": law.get("EngLawName", ""),
            "level": law.get("LawLevel", ""),
            "moj_category": law.get("LawCategory", ""),
            "modified_date": law.get(f["modified_date"], ""),
            "effective_date": law.get("LawEffectiveDate", ""),
            "effective_note": law.get("LawEffectiveNote", ""),
            "abandon_note": law.get(f["abandon_note"], ""),
            "foreword": law.get(f["foreword"], ""),
            "histories": law.get(f["histories"], ""),
            "url": law.get(f["url"], ""),
            "update_date": update_date,
        }

        article_rows = []
        stack: list[str] = []
        seq = 0

        for entry in law.get(f["articles"]) or []:
            content = _fix_typos(entry.get(f["article_content"], "") or "")

            if entry.get(f["article_type"]) == "C":
                depth = _heading_depth(content)
                del stack[depth:]
                # Pad when a level is skipped so depth stays the index.
                while len(stack) < depth:
                    stack.append("")
                stack.append(clean_heading(content))
                continue

            article_no = (entry.get(f["article_no"]) or "").strip()
            article_rows.append(
                {
                    "law_id": law_id,
                    "seq": seq,
                    "article_no": article_no,
                    "article_key": article_key(article_no),
                    "content": content,
                    "chapter_path": " / ".join(p for p in stack if p),
                    **{
                        level: stack[depth] if depth < len(stack) and stack[depth] else None
                        for depth, level in enumerate(LEVELS)
                    },
                    "repealed": is_repealed(content),
                }
            )
            seq += 1

        yield law_row, article_rows
