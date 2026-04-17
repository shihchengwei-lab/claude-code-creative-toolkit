---
name: token-conservation
description: Claude Code agent 的 token 節省行為規範。當專案複雜、context window 吃緊、或用戶明確要求省 token 時載入此 skill。包含 CLAUDE.md 可直接複製的規則片段、agent 派工格式、回報格式、skill 載入策略。適用於任何使用 Claude Code multi-agent 架構的專案。
---

# Token Conservation

給 token 敏感的 Claude Code 專案用的行為約束集合。不是 compaction hook（被動），是行為規則（主動）。

---

## CLAUDE.md 可直接複製的片段

```markdown
## Token 節省規則
- 不重複貼已存在的程式碼，只貼 diff
- 回報用一句話，不寫報告
- subagent 指令要精準，附上檔案路徑與預期輸出格式
- 不解釋為什麼這樣做，做就對了
- 讀檔前先確認是否已在 context 中
- 不要問 user「可以嗎」「要不要」，看決策權限表
```

---

## Agent 派工格式

PM 派工給 subagent 時，用這個四行格式。多一行都是浪費。

```
任務：[一句話描述]
輸入：[檔案路徑或資料]
輸出：[預期產物與路徑]
驗收：[通過條件]
```

### 為什麼四行
- 「任務」讓 agent 知道做什麼
- 「輸入」省去 agent 自己找檔案的搜索 token
- 「輸出」讓 agent 不用猜你要什麼格式
- 「驗收」讓 agent 自行判斷完成沒，不需要回來問

---

## 回報格式

Agent 回報 PM 時，限定格式：

```
完成：✅ [模組名] → [產物路徑]
阻塞：🚫 [問題一句話] — 需要：[你要什麼]
進度：📍 Phase X — [完成數]/[總數]
```

禁止寫超過兩行的回報。如果需要詳細說明，寫進檔案讓 PM 自己讀。

---

## Skill 載入策略

問題：agent 啟動時把所有 skill 讀進來 → context 爆炸。

規則：
1. Agent 啟動時只讀 SKILL.md 的 frontmatter（~100 tokens）
2. 只在任務涉及該 skill 領域時才載入完整 SKILL.md
3. 載入前先讀 frontmatter 確認相關性
4. 一個任務最多同時載入 2 個 skill，超過代表任務該拆分

寫進你的 agent 定義：
```markdown
## Skills
- **skill-a** — `skills/skill-a/SKILL.md`（任務涉及 X 時載入）
- **skill-b** — `skills/skill-b/SKILL.md`（任務涉及 Y 時載入）
注意：只在任務涉及該領域時才載入，不要預載。
```

---

## 決策權限表

減少 user 來回 = 減少 token。把這張表放進 CLAUDE.md，agent 一看就知道該不該問。

```markdown
| 事項 | 自行決定 | 需 user 確認 |
|------|---------|-------------|
| 技術架構 | ✅ | |
| 命名規範 | ✅ | |
| 免費套件選擇 | ✅ | |
| Bug 修復 | ✅ | |
| 重構 | ✅ | |
| UI 風格 | | ✅ |
| 新增 feature | | ✅ |
| 付費服務 | | ✅ |
| 刪除已確認 feature | | ✅ |
```

根據你的專案調整內容，格式保留。

---

## 讀檔節省

- 讀檔前先問：這個檔案的內容是否已經在 context 中？
- 如果在，不重複讀
- 如果只需要檔案的一部分，用 Grep 定位後只讀該段
- 長檔案（>200 行）先讀目錄/結構，再決定讀哪段

---

## Session 邊界節省

每次 session 結束前，PM 自動寫一份狀態摘要：

```markdown
# Session State — [日期]
## 已完成
- [清單]
## 進行中
- [清單 + 卡在哪]
## 下次啟動要做
- [清單]
## 重要決策記錄
- [清單]
```

存到 `docs/session-state.md`。下次啟動時 PM 先讀這份，不需要重讀整個專案歷史。

---

## 適用建議

- 個人開發者 / 小團隊 → 全部採用
- 大團隊有充足 API credit → 挑「派工格式」和「回報格式」用就好
- 搭配 ECC 的 strategic-compact → 行為約束（主動）+ compaction hook（被動）雙管齊下
