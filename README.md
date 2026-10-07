# twlaw

在本機查詢全國法規資料庫。

English: [README.en.md](https://github.com/yhc0712/twlaw/blob/main/README.en.md)

```python
>>> from twlaw import LawDB
>>> db = LawDB()
>>> article = db.get_article("所得稅法", 94)
>>> article.chapter_path
'第四章 稽徵程序 / 第四節 扣繳'
>>> article.content[:30]
'扣繳義務人於扣繳稅款時，應隨時通知納稅義務人，並依第九十二條'
```

法務部的 [Open API](https://law.moj.gov.tw/api/swagger/index.html) 只提供整包 zip，不能搜尋，也不能只取一條。
`twlaw` 把整包資料下載下來，解析成一條一條的條文，標上所屬的編章節，存進本機 SQLite。
之後的查詢都不需要網路。

## 安裝

```bash
pip install twlaw
```

需要 Python 3.11 以上。

## 第一次使用：建立資料庫

```python
from twlaw import LawDB

db = LawDB()
db.refresh()
```

`refresh()` 會下載法律和命令的中、英文版，共四份資料，存成 `~/.twlaw/law.db`。
只需要跑一次。之後 `LawDB()` 會直接開啟這個檔案。

只需要中文法律的話，可以縮小範圍：

```python
db.refresh(categories=("law",), langs=("zh",))
```

資料庫還沒建立就查詢，會拋出 `RuntimeError`。程式裡可以這樣處理：

```python
db = LawDB()
if db.is_empty:
    db.refresh()
```

想把資料庫放在別處，傳入路徑即可。`LawDB` 也可以當 context manager 用：

```python
with LawDB("./law.db") as db:
    ...
```

資料庫是一般的 SQLite 檔案，有 `laws` 和 `articles` 兩張表，也可以用其他語言或 DB Browser for SQLite 之類的工具直接開啟。

## 查一部法規

```python
law = db.get_law("所得稅法")

law.id              # 'G0340003'
law.level           # '法律'
law.moj_category    # '行政＞財政部＞賦稅目'
law.modified_date   # '20260911'
len(law.articles)   # 198
```

可以用法規名稱或法規代碼查。名稱必須完全相同：

```python
db.get_law("G0340003")   # 所得稅法
db.get_law("所得稅")      # None，不會猜你要哪一部
```

這樣設計是因為很多法規名稱互為前綴，例如「所得稅法」和「所得稅法施行細則」。
不確定全名時，用 `list_laws()` 找：

```python
for law in db.list_laws(name_like="所得稅法"):
    print(law.id, law.name)
```

## 查一條條文

條號用引用時的寫法：`94` 是第 94 條，`"4-1"` 是第 4 條之一。

```python
db.get_article("所得稅法", 94)
db.get_article("所得稅法", "4-1")
db.get_article("所得稅法", 9999)   # None
```

`get_law()` 回傳的 `law.articles` 也用同樣的條號取值：

```python
law = db.get_law("所得稅法")
law.articles[94]          # 第 94 條
law.articles["4-1"]       # 第 4 條之一
law.articles.get(9999)    # None；用 law.articles[9999] 會拋出 KeyError
```

`law.articles[0]` 不是第一條。條號和位置對不起來，因為「之一」條文夾在中間：

```python
>>> [a.article_key for a in law.articles][:8]
['1', '2', '3', '3-1', '3-2', '3-3', '3-4', '4']
```

要依順序處理，直接迭代：

```python
for article in law.articles:
    print(article.article_no, article.content)
```

## 章節

每條條文都帶著它所在的編、章、節、款、目：

```python
>>> a = db.get_article("民法", 1031)
>>> a.chapter_path
'第四編 親屬 / 第二章 婚姻 / 第四節 夫妻財產制 / 第三款 約定財產制 / 第一目 共同財產制'
>>> a.part, a.chapter, a.section
('第四編 親屬', '第二章 婚姻', '第四節 夫妻財產制')
>>> a.subsection, a.item
('第三款 約定財產制', '第一目 共同財產制')
```

法規沒有那一層時是 `None`。所得稅法沒有編，所以 `part` 是 `None`；沒有分章的法規，`chapter_path` 是空字串。

依章分組：

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

## 搜尋

```python
for hit in db.search("扣繳義務人", limit=3):
    print(hit.law_name, hit.article_no, hit.chapter_path)
```

```
所得稅法 第 94 條 第四章 稽徵程序 / 第四節 扣繳
所得稅法施行細則 第 85-2 條 第四章 稽徵程序
所得稅法 第 114 條 第五章 獎懲
```

結果依相關性排序，預設最多 50 筆。條文內容命中的排名高於只有章節名稱命中。可以篩選：

```python
db.search("營業稅", category="law")          # 只查法律，不含命令
db.search("withholding agent", lang="en")   # 英文版
```

搜尋結果和 `get_article()` 回傳的是同一種物件，可以直接用來回查：

```python
hit = db.search("扣繳義務人")[0]
db.get_article(hit.law_name, hit.article_key)
```

一到兩個字的查詢（例如「稅」）會改用逐筆比對：結果依法規和條號排序，不依相關性，速度也比一般查詢慢。

## 已刪除的條文

已刪除的條文仍保留條號，內容只剩「（刪除）」。`search()` 預設不回傳這些條文：

```python
db.search("營業稅")                          # 不含已刪除條文
db.search("營業稅", include_repealed=True)   # 包含
```

只有整條內容就是刪除標記時才算已刪除。條文內只有某一款刪除，例如民事訴訟法第 389 條的「二、（刪除）」，
這條仍然有效，照樣搜尋得到。可以用 `article.repealed` 判斷：

```python
>>> a = db.get_article("所得稅法", 12)
>>> a.repealed, a.content
(True, '（刪除）')
```

## 更新資料

法務部會不定期更新資料。`update_date()` 回傳本機資料的發布日期：

```python
db.update_date()   # '2026/9/24 上午 12:00:00'
```

要更新就再跑一次 `refresh()`。它會整批取代，不會產生重複資料。
多個程式可以同時讀取同一個資料庫，`refresh()` 執行期間其他程式也能繼續查詢。

升級 `twlaw` 後，若資料庫格式有變，舊的資料庫在開啟時會被清空，需要重新 `refresh()`。
[CHANGELOG](CHANGELOG.md) 會註明哪些版本需要這樣做。

## API

### `LawDB`

| 方法 | 回傳 | 說明 |
| --- | --- | --- |
| `LawDB(path=None)` | | 開啟資料庫，預設 `~/.twlaw/law.db` |
| `refresh(categories=("law", "order"), langs=("zh", "en"))` | `dict` | 下載並取代資料；回傳每份資料的法規數 |
| `get_law(law, lang="zh")` | `Law \| None` | 依代碼或名稱取一部法規，含全部條文 |
| `get_article(law, article, lang="zh")` | `Article \| None` | 依條號取一條 |
| `search(query, lang="zh", category=None, limit=50, include_repealed=False)` | `list[Article]` | 全文搜尋 |
| `list_laws(category=None, lang="zh", name_like=None)` | `list[Law]` | 列出法規，不含條文 |
| `update_date(category="law", lang="zh")` | `str \| None` | 資料發布日期 |
| `is_empty` | `bool` | 是否還沒有資料 |
| `close()` | | 關閉連線 |

`category` 是 `"law"`（法律）或 `"order"`（命令）；`lang` 是 `"zh"` 或 `"en"`。

### `Article`

| 欄位 | 範例 |
| --- | --- |
| `law_id` | `'G0340003'` |
| `law_name` | `'所得稅法'` |
| `category` | `'law'` |
| `article_no` | `'第 4-1 條'`，原始條號 |
| `article_key` | `'4-1'`，可傳給 `get_article()` 的條號 |
| `content` | 條文內容；項與款以換行分隔 |
| `chapter_path` | `'第一章 總則 / 第一節 一般規定'` |
| `part` `chapter` `section` `subsection` `item` | 編、章、節、款、目，沒有時為 `None` |
| `repealed` | 是否已刪除 |
| `seq` | 在法規中的順序，從 0 開始 |

### `Law`

`id`、`name`、`name_en`、`level`、`category`、`moj_category`、`modified_date`、`effective_date`、
`effective_note`、`abandon_note`、`foreword`、`histories`、`url`、`update_date`，以及 `articles`。
`list_laws()` 回傳的 `Law` 沒有載入條文，`articles` 是空的。

`Article` 和 `Law` 都是不可變的 dataclass。要轉成 dict 或 JSON，用 `dataclasses.asdict()`。

## 資料來源與授權

`twlaw` 以 MIT 授權釋出，套件本身不含法規資料。資料在執行 `refresh()` 時取自
[法務部全國法規資料庫](https://law.moj.gov.tw/)，依[政府資料開放授權條款－第1版](https://data.gov.tw/license)提供，
使用時須註明出處，例如：

> 資料來源：法務部全國法規資料庫 https://law.moj.gov.tw/

`twlaw` 的章節路徑和標題格式是解析後的結果，不是官方文字。正式引用請以法務部公布的原文為準。
