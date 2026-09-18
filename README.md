# twlaw

Queryable local access to Taiwan's national laws and regulations database
(全國法規資料庫).

繁體中文說明：[README.zh-TW.md](README.zh-TW.md)

## Why

The MOJ Open API only serves whole-database zip dumps. There is no search, no
per-record lookup, and chapter headings are flattened into the article list with
indentation as the only clue to structure. `twlaw` downloads those dumps,
reconstructs the hierarchy for every article, and stores the result in a local
SQLite database you can query.

## Install

```bash
uv add twlaw          # or: pip install twlaw
```

## Getting started

Building the local database is a separate, explicit step. Do it once:

```python
from twlaw import LawDB

db = LawDB()          # opens ~/.twlaw/law.db (created if missing)
db.refresh()          # downloads all 4 datasets — ~2 min, ~520 MB on disk
```

After that, every query is local and fast (single-digit milliseconds). Nothing
touches the network again until you call `refresh()` yourself.

```python
from twlaw import LawDB

db = LawDB()                              # reopens the existing database
if db.is_empty:                           # guard for first run
    db.refresh()

for hit in db.search("扣繳義務人", limit=5):
    print(hit["law_name"], hit["article_no"])
    print("  ", hit["chapter_path"])
```

```
所得稅法 第 94 條
   第 四 章 稽徵程序 / 第 四 節 扣繳
```

## API

### `LawDB(path=None)`

Opens (and creates if needed) the SQLite store. Defaults to `~/.twlaw/law.db`;
pass a path to keep it elsewhere. Usable as a context manager.

```python
with LawDB("./law.db") as db:
    ...
```

### `db.refresh(categories=("law", "order"), langs=("zh", "en"))`

Re-downloads datasets and replaces their rows. Takes ~2 minutes for everything.
Returns how many laws were stored per dataset. Narrow the scope if you only
need part of it:

```python
db.refresh(categories=("law",), langs=("zh",))   # Chinese statutes only, ~20 s
```

Safe to re-run — rows are replaced, not duplicated.

### `db.search(query, lang="zh", category=None, limit=50, include_repealed=False)`

Full-text search over article text. Returns a list of dicts, best match first:

| key | meaning |
| --- | --- |
| `law_id` | law code, e.g. `G0340003` |
| `law_name` | e.g. `所得稅法` |
| `category` | `law` or `order` |
| `article_no` | e.g. `第 94 條` |
| `article_key` | citable number, e.g. `94` or `4-1` |
| `content` | the article text |
| `chapter_path` | reconstructed hierarchy |
| `seq` | article position within the law |

```python
db.search("營業稅", category="law")        # statutes only, skip 命令
db.search("income tax", lang="en")        # English corpus
db.search("設籍", include_repealed=True)   # include （刪除） articles
```

### `db.get_law(law, lang="zh")`

One law with all its articles, or `None` if not found. Takes a law **name** or
a MOJ law code — use whichever you have. Returns the metadata fields plus an
`articles` list of `{seq, article_no, content, chapter_path}`.

```python
law = db.get_law("所得稅法")        # by name
law = db.get_law("G0340003")       # same law, by code

law["name"]              # 所得稅法
law["id"]                # G0340003
law["modified_date"]     # 20260911
len(law["articles"])     # 198
```

Names match exactly, not by prefix — `"所得稅法"` gives you 所得稅法, never
所得稅法施行細則. Use `list_laws(name_like=...)` or `search()` when you don't
know the exact name.

### `db.get_article(law, article, lang="zh")`

One article by the number you'd cite it by, or `None` if there is no such
article. `4` is 第 4 條 and `"4-1"` is 第 4 條之一 — you never deal with list
positions or MOJ's label strings.

```python
db.get_article("所得稅法", 1)       # 第 1 條
db.get_article("所得稅法", "4-1")   # 第 4 條之一 — a distinct article from 第 4 條
```

```python
{'seq': 8, 'article_no': '第 4-1 條', 'article_key': '4-1',
 'content': '自中華民國七十九年一月一日起，證券交易所得停止課徵所得稅…',
 'chapter_path': '第 一 章 總則 / 第 一 節 一般規定',
 'law_id': 'G0340003', 'law_name': '所得稅法'}
```

Every article everywhere carries this `article_key`, so a `search()` hit can be
re-fetched or cited directly:

```python
hit = db.search("扣繳義務人")[0]
db.get_article(hit["law_name"], hit["article_key"])
```

### `db.list_laws(category=None, lang="zh", name_like=None)`

Law metadata without article bodies — for browsing or building a picker.

```python
db.list_laws(name_like="所得稅")
db.list_laws(category="law")
```

### `db.update_date()` / `db.is_empty`

MOJ's own publication date for the stored data, and whether anything is stored
yet. Use `update_date()` to decide if a `refresh()` is worthwhile.

## Examples

Look up a single article:

```python
print(db.get_article("所得稅法", "4-1")["content"])
```

Read one law article by article:

```python
law = db.get_law("所得稅法")

for a in law["articles"]:
    print(a["article_no"], a["chapter_path"])
    print(a["content"])
```

Find which laws mention a term:

```python
for hit in db.search("營業稅", limit=10):
    print(hit["law_name"], hit["article_no"])
```

List every tax law, using MOJ's own classification:

```python
for l in db.list_laws():
    if "賦稅" in l["moj_category"]:
        print(l["id"], l["name"])
```

### Chunking for RAG

Each article already carries its chapter path, so a chunk is interpretable on
its own without extra work:

```python
law = db.get_law("所得稅法")

for a in law["articles"]:
    chunk = f"{law['name']} {a['article_no']}\n{a['chapter_path']}\n{a['content']}"
    print(chunk)
```

## Coverage

| dataset | records |
| --- | --- |
| laws, Chinese | 1,347 |
| orders, Chinese | 10,451 |
| laws, English | 972 |
| orders, English | 2,206 |

English records are a separate, smaller corpus — not a translation of every
Chinese record. A law present in both shares the same `law_id`, so
`get_law(id, lang="en")` gives you the English text of the same statute.

## Notes

- **Concurrency.** WAL mode is on, so many processes can read at once. Only
  `refresh()` writes.
- **Search.** FTS5 with the `trigram` tokenizer, which is what makes Chinese
  substring search work: the default `unicode61` treats an unbroken run of CJK
  as one token, which would find 50 articles for 所得稅 instead of ~1,400.
  Queries under 3 characters fall back to `LIKE`.
- **Storage.** Plain SQLite tables (`laws`, `articles`), so the file is readable
  from any language, not only Python.

## Data source

Data comes from the [MOJ Open API](https://law.moj.gov.tw/api/swagger/index.html).
The MOJ database is authoritative; treat this as a convenience mirror and cite
the official text for anything that matters.
