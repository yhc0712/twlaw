# twlaw

以本機 SQLite 查詢全國法規資料庫（法務部 Open API）的 Python 套件。

English: [README.md](README.md)

## 為什麼需要這個套件

法務部 Open API 只提供「整包資料庫」的 zip 下載：沒有搜尋、沒有單筆查詢，而且
章節標題和條文被壓平在同一個清單裡，只能靠縮排判斷層級。`twlaw` 負責把這些資料
下載下來、重建每一條條文的章節層級，存成可查詢的本機 SQLite 資料庫。

## 安裝

```bash
uv add twlaw          # 或 pip install twlaw
```

## 快速開始

建立本機資料庫是一個獨立的明確步驟，只需要做一次：

```python
from twlaw import LawDB

db = LawDB()          # 開啟 ~/.twlaw/law.db（不存在就建立）
db.refresh()          # 下載全部四份資料集 — 約 2 分鐘，硬碟約 520 MB
```

之後所有查詢都在本機執行，速度是毫秒級。除非你自己再呼叫 `refresh()`，
不會再連網。

```python
from twlaw import LawDB

db = LawDB()                              # 重新開啟既有資料庫
if db.is_empty:                           # 第一次執行時的保護
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

開啟（必要時建立）SQLite 資料庫。預設路徑為 `~/.twlaw/law.db`，可傳入自訂路徑。
支援 context manager：

```python
with LawDB("./law.db") as db:
    ...
```

### `db.refresh(categories=("law", "order"), langs=("zh", "en"))`

重新下載資料並取代原有資料列。全部下載約需 2 分鐘，回傳每份資料集存入的法規數量。
只需要部分資料時可以縮小範圍：

```python
db.refresh(categories=("law",), langs=("zh",))   # 只要中文法律，約 20 秒
```

可重複執行——資料是「取代」而非「累加」，不會產生重複。

### `db.search(query, lang="zh", category=None, limit=50, include_repealed=False)`

對條文內容做全文檢索，回傳 dict 清單，相關性高的在前：

| 欄位 | 說明 |
| --- | --- |
| `law_id` | 法規代碼，例如 `G0340003` |
| `law_name` | 法規名稱，例如 `所得稅法` |
| `category` | `law`（法律）或 `order`（命令） |
| `article_no` | 條號，例如 `第 94 條` |
| `article_key` | 可引用的條號，例如 `94`、`4-1` |
| `content` | 條文內容 |
| `chapter_path` | 重建後的章節層級 |
| `seq` | 該條在法規中的順序 |

```python
db.search("營業稅", category="law")        # 只查法律，排除命令
db.search("income tax", lang="en")        # 查英文版
db.search("設籍", include_repealed=True)   # 包含已刪除條文
```

### `db.get_law(law, lang="zh")`

取得單一法規及其全部條文；查不到時回傳 `None`。可以傳**法規名稱**或法規代碼，
用手上有的那個即可。除了法規的後設資料外，還包含 `articles` 清單，
每筆為 `{seq, article_no, content, chapter_path}`。

```python
law = db.get_law("所得稅法")        # 用名稱
law = db.get_law("G0340003")       # 同一部法規，用代碼

law["name"]              # 所得稅法
law["id"]                # G0340003
law["modified_date"]     # 20260911
len(law["articles"])     # 198
```

名稱採**完全比對**，不做前綴比對——傳 `"所得稅法"` 一定拿到所得稅法，
不會拿到所得稅法施行細則。不確定確切名稱時，
先用 `list_laws(name_like=...)` 或 `search()` 找。

### `db.get_article(law, article, lang="zh")`

依「引用時會寫的條號」取得單一條文，查不到時回傳 `None`。
`4` 就是第 4 條，`"4-1"` 就是第 4 條之一——不需要處理清單位置，
也不需要自己剖析法務部的條號字串。

```python
db.get_article("所得稅法", 1)       # 第 1 條
db.get_article("所得稅法", "4-1")   # 第 4 條之一，與第 4 條是不同條文
```

```python
{'seq': 8, 'article_no': '第 4-1 條', 'article_key': '4-1',
 'content': '自中華民國七十九年一月一日起，證券交易所得停止課徵所得稅…',
 'chapter_path': '第 一 章 總則 / 第 一 節 一般規定',
 'law_id': 'G0340003', 'law_name': '所得稅法'}
```

每一條條文都帶有 `article_key`，因此 `search()` 的結果可以直接回查或引用：

```python
hit = db.search("扣繳義務人")[0]
db.get_article(hit["law_name"], hit["article_key"])
```

### `db.list_laws(category=None, lang="zh", name_like=None)`

只列出法規的後設資料（不含條文內容），適合瀏覽或做選單。

```python
db.list_laws(name_like="所得稅")
db.list_laws(category="law")
```

### `db.update_date()` / `db.is_empty`

分別回傳法務部對這批資料的發布日期，以及本機是否已有資料。
可用 `update_date()` 判斷是否值得重新 `refresh()`。

## 章節層級重建

這是本套件的核心價值。法務部把章節標題與條文放在同一個清單，
層級只靠縮排表示：

```json
{"ArticleType": "C", "ArticleNo": "",       "ArticleContent": "   第 一 章 總則"}
{"ArticleType": "C", "ArticleNo": "",       "ArticleContent": "      第 一 節 一般規定"}
{"ArticleType": "A", "ArticleNo": "第 1 條", "ArticleContent": "所得稅分為綜合所得稅及…"}
```

`twlaw` 會將其還原成每一條條文自身攜帶的明確路徑：

```python
law = db.get_law("所得稅法")
law["articles"][0]
# {'seq': 0, 'article_no': '第 1 條',
#  'content': '所得稅分為綜合所得稅及營利事業所得稅。',
#  'chapter_path': '第 一 章 總則 / 第 一 節 一般規定'}
```

## 範例

查單一條文：

```python
print(db.get_article("所得稅法", "4-1")["content"])
```

逐條讀取一部法規：

```python
law = db.get_law("所得稅法")

for a in law["articles"]:
    print(a["article_no"], a["chapter_path"])
    print(a["content"])
```

查哪些法規提到某個詞：

```python
for hit in db.search("營業稅", limit=10):
    print(hit["law_name"], hit["article_no"])
```

用法務部的分類列出所有稅法：

```python
for l in db.list_laws():
    if "賦稅" in l["moj_category"]:
        print(l["id"], l["name"])
```

### 切 chunk 做 RAG

每一條條文都已經帶著自己的章節路徑，因此 chunk 單獨看也能理解，
不需要額外處理：

```python
law = db.get_law("所得稅法")

for a in law["articles"]:
    chunk = f"{law['name']} {a['article_no']}\n{a['chapter_path']}\n{a['content']}"
    print(chunk)
```

## 資料涵蓋範圍

| 資料集 | 筆數 |
| --- | --- |
| 法律（中文） | 1,347 |
| 命令（中文） | 10,451 |
| 法律（英文） | 972 |
| 命令（英文） | 2,206 |

英文資料是獨立且較小的語料，並非每筆中文法規都有英譯。同時存在兩種語言的法規
共用同一個 `law_id`，因此 `get_law(id, lang="en")` 可取得同一部法規的英文版本。

## 技術說明

- **並行查詢**：已啟用 WAL 模式，多個 process 可同時讀取；只有 `refresh()` 會寫入。
- **檢索**：使用 FTS5 搭配 `trigram` tokenizer，這是中文子字串檢索能正確運作的關鍵。
  預設的 `unicode61` 會把連續中文視為單一 token，查「所得稅」只會找到約 50 筆，
  而非實際的約 1,400 筆。查詢字串少於 3 個字時會改用 `LIKE`。
- **儲存格式**：單純的 SQLite 資料表（`laws`、`articles`），
  因此這個檔案不限於 Python，其他語言也能直接讀取。

## 資料來源

資料取自[法務部全國法規資料庫 Open API](https://law.moj.gov.tw/api/swagger/index.html)。
法務部資料庫為權威來源；本套件僅為便利用途的本機副本，
重要事項請以官方公布之法規原文為準。
