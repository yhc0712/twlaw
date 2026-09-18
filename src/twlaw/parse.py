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

# "第 4-1 條" / "Article 4-1" -> "4-1". Both languages also use a bare number
# for a handful of appendix-style entries.
_ARTICLE_NO_RE = re.compile(r"(\d+(?:-\d+)?)")


def article_key(article_no: str) -> str:
    """Return the citable number in an article label, e.g. ``第 4-1 條`` -> ``4-1``."""
    match = _ARTICLE_NO_RE.search(article_no or "")
    return match.group(1) if match else ""

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
            content = entry.get(f["article_content"], "") or ""

            if entry.get(f["article_type"]) == "C":
                depth = _heading_depth(content)
                del stack[depth:]
                # Pad when a level is skipped so depth stays the index.
                while len(stack) < depth:
                    stack.append("")
                stack.append(content.strip())
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
                }
            )
            seq += 1

        yield law_row, article_rows
