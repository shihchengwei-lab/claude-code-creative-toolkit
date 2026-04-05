# Design Integrity Guard

**讓 Claude Code agent 在自主開發時，不背叛你的產品靈魂。**

適用場景：任何有「不可妥協的設計原則」的專案——遊戲的精神方向、醫療 app 的倫理準則、教育產品的教學理念、品牌 app 的調性底線。

## 問題

Claude Code agent 越自主，越容易在長 session 中漸漸偏離你的設計初衷。CLAUDE.md 管得了技術規範，管不了精神方向。你需要的不只是「寫得好」，是「不走味」。

## 架構

```
your-project/
├── CLAUDE.md                          # 錨點（放不可違背的一句話判準）
├── docs/
│   └── design-principles.md           # 你的產品靈魂文件（canon）
├── agents/
│   └── content-guardian.md            # 守衛 agent 定義
└── skills/
    └── design-integrity-guard/
        ├── SKILL.md                   # 判準規則（本 plugin 核心）
        └── references/
            └── customization-guide.md # 如何客製化
```

## 三層防護

1. **CLAUDE.md 錨點** — 3-5 條生死線，agent 啟動時讀取
2. **design-principles.md** — 完整的設計原則文件，guardian agent 查閱用
3. **design-integrity-guard skill** — 具體判準規則，任何 agent 產出玩家/用戶可見內容時自動載入

## 安裝

把 `skills/design-integrity-guard/` 整個資料夾複製到你的專案 `skills/` 下，然後：

1. 寫你的 `docs/design-principles.md`（見下方模板）
2. 改 `SKILL.md` 裡的判準（替換範例內容）
3. 在 CLAUDE.md 加錨點
4. 如果需要 guardian agent，複製 `agents/content-guardian.md` 並客製化

## 快速開始：寫你的 design-principles.md

先看範例 → 再填模板：
- 📖 **範例**：[`docs/design-principles-example.md`](./docs/design-principles-example.md) — 一份填好的完整範例
- 📝 **模板**：[`docs/design-principles-template.md`](./docs/design-principles-template.md) — 複製這份，改名為 `design-principles.md`，填入你的答案
- 🔧 **客製化指南**：[`skills/design-integrity-guard/references/customization-guide.md`](./skills/design-integrity-guard/references/customization-guide.md) — 從模板到上線的完整步驟

回答以下問題，你就有了第一版：

```markdown
# [產品名] 設計原則

## 這個產品是什麼
一句話。

## 絕對不能變成什麼
列 3-5 條。這是你的生死線。

## 用戶應該感受到什麼
列出氛圍關鍵詞。

## 用戶絕對不應該感受到什麼
列出禁止氛圍。

## 禁用詞彙
哪些詞一出現就代表走味了。

## 最終判準
一句話。如果只能記住一條規則，是哪條？
```

## 運作原理

guardian agent 在兩個時機介入：

- **主動撰寫**：被 PM 派工寫用戶可見文字時，載入 skill 依判準撰寫
- **被動守衛**：其他 agent 交付含用戶可見文字的產出時，自動審查

審查不通過 → 標註問題退回修改，不需要打擾 user。

## 來自

泛化自一個重視精神方向不可偏離的產品專案。原始架構包含三層設計原則文件、文案守衛 agent、多類型語氣規範等實戰驗證過的模式。
