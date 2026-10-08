# 待辦事項

## 發布

- [x] 到 [GitHub Actions](https://github.com/yhc0712/twlaw/actions) 確認 v0.2.0、v0.2.1 的 publish 是否完成；
      若停在 "Waiting"，按 Review deployments 核准。v0.2.1 已包含 0.2.0 的全部內容，0.2.0 可以不核准。
- [x] 確認 https://pypi.org/project/twlaw/ 顯示中文 README，側欄有 Changelog 連結。
- [ ] 在 GitHub 建立 v0.2.0、v0.2.1 的 Release，內容貼 CHANGELOG.md 對應段落。

## 資料品質（預計 v0.3.0）

先決定：直接改寫 `content`，還是保留原文、另存一份正規化文字供搜尋。
改寫的話要在 README「條文內容除了下列修正」清單補上一項。

- [ ] **私用區造字（PUA）**：中文條文有 96 條（74 部法規）含 U+E000–U+F8FF 的造字，
      例如 `製造酒類之白、紅`。一般字型顯示為方框，搜尋標準字也找不到。
      做法：建立 PUA 到標準字的對照表，在 `parse.py` 轉換；對不到的保留原樣。
      [mojLawSplit](https://github.com/kong0107/mojLawSplit) 有類似對照可參考（MIT，引用時註明出處）。
      對照表填寫中：`pua-review.xlsx`（未進版控）。
- [x] **注音「ㄧ」當成「一」**：中文條文有 20 條把 U+3127「ㄧ」當成 U+4E00「一」。
      全部都是誤植，`parse.py` 一律改成「一」，README 已註明。

統計數字來自 2026/9/24 發布的資料，法務部更新後數字會變。

## 之後再考慮

- [ ] 附件（附表、附圖）：`Law.attachments` 已有檔名與下載連結，但附件屬於哪一條、附件內容都沒有處理。
      內容多為 PDF、DOC，少數是圖片，要搜尋得先抽文字或 OCR。
