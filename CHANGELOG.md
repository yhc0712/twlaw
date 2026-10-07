# 更新紀錄

本檔記錄每個版本的重要變更。格式依循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，
版本號依循 [Semantic Versioning](https://semver.org/lang/zh-TW/)：1.0 之前，破壞性變更會升 minor 版號。

## [Unreleased]

## [0.2.1] - 2026-10-07

### 變更

- 改善 `get_article()` 與 `get_law()` 的查詢效能。既有的資料庫在開啟時會自動補上索引，不需要重新 `refresh()`。
- 重寫中、英文 README，依實際使用順序說明。
- PyPI 頁面新增 Changelog 連結。

## [0.2.0] - 2026-10-07

本版含破壞性變更，升級前請先看「變更」一節。資料庫格式也已更新，升級後須重新執行一次 `refresh()`。

### 新增

- `Article`、`Law` 資料類別，以及 `Articles` 條文集合，皆可從 `twlaw` 直接匯入。
- `Article.part`／`chapter`／`section`／`subsection`／`item`：依序為所屬的編、章、節、款、目，
  每層一個欄位；法規沒有該層時為 `None`。
- `Article.repealed`：條文是否已刪除。
- `law.articles` 可用條號取條文：`law.articles[1]` 是第 1 條，`law.articles["4-1"]` 是第 4 條之一，
  與 `get_article()` 使用相同條號。另提供 `law.articles.get(n)` 與 `n in law.articles`。

### 變更

- **破壞性**：`search()`、`get_article()`、`get_law()`、`list_laws()` 改為回傳不可變的資料類別，不再回傳
  dict。請將 `hit["law_name"]` 改為 `hit.law_name`；需要 dict 時可用 `dataclasses.asdict()`。
- **破壞性**：`law.articles` 改以條號索引，不再以清單位置索引。`law.articles[0]` 會拋出 `KeyError`，
  也不支援切片；需要時請改用 `list(law.articles)`。逐條迭代與 `len()` 不受影響。
- **破壞性**：章節標題經過整理，`chapter_path` 由 `第 四 章 稽徵程序 / 第 四 節 扣繳` 變為
  `第四章 稽徵程序 / 第四節 扣繳`。整理時會去除標記中的空格、統一全形與連續空白，
  並修正原始資料中重複的「第」。
- **破壞性**：資料庫結構版本升為 3。舊版建立的資料庫在開啟時會被清空，須重新 `refresh()`。
- `get_law()` 回傳的每一條條文都帶有 `law_id`、`law_name`、`category`，欄位與 `search()` 結果一致。
- 中文 README 改為 `README.md`，GitHub 與 PyPI 會優先顯示中文說明；英文版移至 `README.en.md`。

### 修正

- `search()` 排除已刪除條文時，原本只要內文提到「刪除」就整條排除，導致 429 條仍有效的中文條文搜尋不到，
  例如內有「更正或刪除」字樣的條文，或只有其中一款標示（刪除）的民事訴訟法第 389 條。
  英文版則反而漏掉 477 條以 `(Repealed.)`、`(Delete)` 等寫法標示的已刪除條文。
  現在只有整條內容就是刪除標記時，才視為已刪除。

## [0.1.0] - 2026-09-18

首次發布。

### 新增

- `LawDB`：下載法務部全國法規資料庫 Open API 的法律與命令（中、英文），存入本機 SQLite。
- 依原始資料的縮排重建編、章、節、款、目層級，每條條文都帶有 `chapter_path`。
- `search()`：以 FTS5 trigram 全文檢索條文，可依語言、類別篩選；少於 3 個字的查詢改用 `LIKE`。
- `get_law()`、`get_article()`：以法規名稱或代碼查詢；`get_article()` 以引用條號查詢，例如 `"4-1"`。
- `list_laws()`、`update_date()`、`is_empty`。
- 以 tag 觸發、經 trusted publishing 發布至 PyPI。

[Unreleased]: https://github.com/yhc0712/twlaw/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/yhc0712/twlaw/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/yhc0712/twlaw/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/yhc0712/twlaw/releases/tag/v0.1.0
