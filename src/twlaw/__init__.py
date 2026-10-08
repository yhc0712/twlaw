"""Queryable local access to Taiwan's national laws and regulations database.

    from twlaw import LawDB

    db = LawDB()
    db.refresh()                       # download and build the local store
    db.search("所得稅")                 # full-text search across articles
    db.get_law("所得稅法")              # one law with chapter-aware articles
    db.get_article("所得稅法", "4-1")   # 第 4 條之一
"""

from .db import DEFAULT_PATH, SCHEMA_VERSION, LawDB
from .fetch import CATEGORIES, LANGS
from .models import Article, Articles, Attachment, Law

__all__ = ["LawDB", "Law", "Article", "Articles", "Attachment", "DEFAULT_PATH", "SCHEMA_VERSION", "CATEGORIES", "LANGS"]
