# twlaw

Query Taiwan's national laws and regulations database (全國法規資料庫) locally.

繁體中文：[README.md](README.md)

```python
>>> from twlaw import LawDB
>>> db = LawDB()
>>> article = db.get_article("所得稅法", 94)
>>> article.chapter_path
'第四章 稽徵程序 / 第四節 扣繳'
>>> article.content[:30]
'扣繳義務人於扣繳稅款時，應隨時通知納稅義務人，並依第九十二條'
```

The Ministry of Justice [Open API](https://law.moj.gov.tw/api/swagger/index.html) only serves whole-database
zip files: no search, no way to fetch one article. `twlaw` downloads those files, splits them into
articles, labels each article with its part, chapter and section, and stores the result in a local
SQLite database. Queries after that never touch the network.

## Install

```bash
pip install twlaw
```

Requires Python 3.11 or later.

## First run: build the database

```python
from twlaw import LawDB

db = LawDB()
db.refresh()
```

`refresh()` downloads laws and orders in Chinese and English, four datasets in all, into
`~/.twlaw/law.db`. You do this once; afterwards `LawDB()` just opens that file.

If you only need Chinese statutes, narrow it down:

```python
db.refresh(categories=("law",), langs=("zh",))
```

Querying before the database is built raises `RuntimeError`. In a program:

```python
db = LawDB()
if db.is_empty:
    db.refresh()
```

To keep the database somewhere else, pass a path. `LawDB` also works as a context manager:

```python
with LawDB("./law.db") as db:
    ...
```

The database is a plain SQLite file with two tables, `laws` and `articles`, so you can also open it
from other languages or with a tool such as DB Browser for SQLite.

## Look up a law

```python
law = db.get_law("所得稅法")

law.id              # 'G0340003'
law.level           # '法律'
law.moj_category    # '行政＞財政部＞賦稅目'
law.modified_date   # '20260911'
len(law.articles)   # 198
```

Look a law up by name or law code. Names must match exactly:

```python
db.get_law("G0340003")   # 所得稅法
db.get_law("所得稅")      # None; it won't guess
```

Exact matching matters because law names often prefix each other, such as 所得稅法 and
所得稅法施行細則. If you don't know the full name, find it with `list_laws()`:

```python
for law in db.list_laws(name_like="所得稅法"):
    print(law.id, law.name)
```

## Look up an article

Use the number as you would cite it: `94` is 第 94 條 and `"4-1"` is 第 4 條之一.

```python
db.get_article("所得稅法", 94)
db.get_article("所得稅法", "4-1")
db.get_article("所得稅法", 9999)   # None
```

`law.articles` from `get_law()` takes the same numbers:

```python
law = db.get_law("所得稅法")
law.articles[94]          # 第 94 條
law.articles["4-1"]       # 第 4 條之一
law.articles.get(9999)    # None; law.articles[9999] raises KeyError
```

`law.articles[0]` is not the first article. Numbers and positions don't line up, because 之一
articles sit between whole numbers:

```python
>>> [a.article_key for a in law.articles][:8]
['1', '2', '3', '3-1', '3-2', '3-3', '3-4', '4']
```

To go through a law in order, iterate:

```python
for article in law.articles:
    print(article.article_no, article.content)
```

## Chapters

Every article carries the part, chapter, section, subsection and item it belongs to
(編, 章, 節, 款, 目):

```python
>>> a = db.get_article("民法", 1031)
>>> a.chapter_path
'第四編 親屬 / 第二章 婚姻 / 第四節 夫妻財產制 / 第三款 約定財產制 / 第一目 共同財產制'
>>> a.part, a.chapter, a.section
('第四編 親屬', '第二章 婚姻', '第四節 夫妻財產制')
>>> a.subsection, a.item
('第三款 約定財產制', '第一目 共同財產制')
```

A level the law doesn't have is `None`. 所得稅法 has no parts, so `part` is `None`. A law with no
chapters at all has an empty `chapter_path`.

Grouping by chapter:

```python
from itertools import groupby

law = db.get_law("所得稅法")
for chapter, articles in groupby(law.articles, key=lambda a: a.chapter):
    print(chapter, len(list(articles)))
```

```
第一章 總則 24
第二章 綜合所得稅 17
第三章 營利事業所得稅 69
第四章 稽徵程序 52
第五章 獎懲 28
第六章 附則 8
```

## Search

```python
for hit in db.search("扣繳義務人", limit=3):
    print(hit.law_name, hit.article_no, hit.chapter_path)
```

```
所得稅法 第 94 條 第四章 稽徵程序 / 第四節 扣繳
所得稅法施行細則 第 85-2 條 第四章 稽徵程序
所得稅法 第 114 條 第五章 獎懲
```

Results are ranked by relevance, 50 at most by default. A match in the article text ranks above a
match in the chapter name only. To filter:

```python
db.search("營業稅", category="law")          # statutes only, no orders
db.search("withholding agent", lang="en")   # English text
```

Search results are the same objects `get_article()` returns, so you can look one up again:

```python
hit = db.search("扣繳義務人")[0]
db.get_article(hit.law_name, hit.article_key)
```

Queries of one or two characters, such as 稅, can't use the search index. They are matched row by
row, ordered by law and article rather than relevance, and are slower than other queries.

## Repealed articles

A repealed article keeps its number, but its text is only a marker such as （刪除） or (Deleted).
`search()` leaves these out by default:

```python
db.search("營業稅")                          # without repealed articles
db.search("營業稅", include_repealed=True)   # with them
```

An article counts as repealed only when its whole text is the marker. If only one item inside it is
repealed, like 二、（刪除） in 民事訴訟法 第 389 條, the article is still in force and still shows up.
Check `article.repealed`:

```python
>>> a = db.get_article("所得稅法", 12)
>>> a.repealed, a.content
(True, '（刪除）')
```

## Abolished laws

Abolished (廢止) laws stay in the database, and `get_law()` and `get_article()` still find them by
name. `list_laws()` and `search()` leave them and their articles out by default:

```python
db.list_laws(include_abolished=True)
db.search("耕者有其田", include_abolished=True)
```

`law.abolished` and `article.abolished` tell whether the law is abolished:

```python
>>> db.get_law("實施耕者有其田條例").abolished
True
```

## Updating the data

The ministry updates its data from time to time. `update_date()` returns the publication date of
your local copy:

```python
db.update_date()   # '2026/9/24 上午 12:00:00'
```

To update, run `refresh()` again. It replaces the data rather than adding to it.
Several programs can read the same database at once, and they can keep querying while `refresh()` runs.

When a new version of `twlaw` changes the database format, an older database is cleared on open and
you need to `refresh()` again. The [CHANGELOG](CHANGELOG.md) says which versions require this.

## API

### `LawDB`

| Method | Returns | Description |
| --- | --- | --- |
| `LawDB(path=None)` | | Open the database, `~/.twlaw/law.db` by default |
| `refresh(categories=("law", "order"), langs=("zh", "en"))` | `dict` | Download and replace data; returns the number of laws per dataset |
| `get_law(law, lang="zh")` | `Law \| None` | One law by code or name, with all its articles |
| `get_article(law, article, lang="zh")` | `Article \| None` | One article by number |
| `search(query, lang="zh", category=None, limit=50, include_repealed=False, include_abolished=False)` | `list[Article]` | Full-text search |
| `list_laws(category=None, lang="zh", name_like=None, include_abolished=False)` | `list[Law]` | List laws without their articles |
| `update_date(category="law", lang="zh")` | `str \| None` | Publication date of the data |
| `is_empty` | `bool` | Whether there is no data yet |
| `close()` | | Close the connection |

`category` is `"law"` (statutes) or `"order"` (regulations); `lang` is `"zh"` or `"en"`.

### `Article`

| Field | Example |
| --- | --- |
| `law_id` | `'G0340003'` |
| `law_name` | `'所得稅法'` |
| `category` | `'law'` |
| `article_no` | `'第 4-1 條'`, the label as published |
| `article_key` | `'4-1'`, the number `get_article()` takes |
| `content` | Article text; paragraphs and items are separated by line breaks |
| `chapter_path` | `'第一章 總則 / 第一節 一般規定'` |
| `part` `chapter` `section` `subsection` `item` | 編, 章, 節, 款, 目; `None` where absent |
| `repealed` | Whether the article is repealed |
| `abolished` | Whether the article's law is abolished |
| `seq` | Position in the law, from 0 |

### `Law`

`id`, `name`, `name_en`, `level`, `category`, `moj_category`, `modified_date`, `effective_date`,
`effective_note`, `abandon_note`, `abolished`, `foreword`, `histories`, `attachments`, `url`, `update_date`, and `articles`.
Laws from `list_laws()` don't load their articles, so `articles` is empty.

`attachments` lists the law's attached files, such as tables (附表) and figures (附圖). Each
`Attachment` has a `name` (the file name) and a `url` (the ministry's download link). `twlaw` doesn't
download the files or search their contents.

```python
>>> db.get_law("立法院組織法").attachments[0].name
'附表 立法委員辦公事務等必要費用之項目及標準.PDF'
```

`Article` and `Law` are frozen dataclasses. Use `dataclasses.asdict()` to get a dict or JSON.

## Related projects

- [mojLawSplit](https://github.com/kong0107/mojLawSplit) splits the same ministry data into one JSON or XML
  file per law and publishes the files on GitHub. Use it if you only need whole laws as files, or
  you aren't working in Python. twlaw instead stores the data in a local database you can query by
  article and search.

## Data source and license

`twlaw` is MIT licensed and ships no legal data. The data is downloaded by `refresh()` from the
[Laws & Regulations Database](https://law.moj.gov.tw/) of the Ministry of Justice, under the
[Open Government Data License v1.0](https://data.gov.tw/license), which requires attribution, for
example:

> Data source: Laws & Regulations Database of the Republic of China (Taiwan), Ministry of Justice — https://law.moj.gov.tw/

Chapter paths and heading formats in `twlaw` are parsed results, not official text. Cite the
ministry's published text for anything that matters.

Article text matches the ministry's text exactly, except for these corrections:

- A few Chinese articles use the bopomofo letter ㄧ (U+3127) where the numeral 一 (U+4E00) is meant,
  as in 二分之ㄧ or 第ㄧ項. `twlaw` replaces every ㄧ with 一, so a search for 一 finds them.
  This follows the character conversion rules (字碼轉換原則) in the
  [mojLawSplit](https://github.com/kong0107/mojLawSplit) README.
