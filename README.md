# Claude Code Creative Toolkit

**讓 Claude Code agent 在自主開發時，不背叛你的產品靈魂。**

三組可複用的 Claude Code 配件，來自實際產品開發的實戰經驗。填補開源社群在「設計完整性」和「非工程角色」上的空白。

## 痛點

Claude Code agent 越自主，越容易在長 session 中偏離設計初衷。CLAUDE.md 管得了技術規範，管不了精神方向。開源社群有 84k+ stars 的工程 agent 框架，但沒有人在做：

- 怎麼讓 agent 不背叛你的設計原則
- 怎麼讓非工程角色（文案、美術）也能被 PM agent 管理
- 怎麼在 context window 吃緊時靠行為約束省 token

## 包含什麼

### 1. [Design Integrity Guard](./design-integrity-guard/)
設計完整性守衛。三層防護架構：CLAUDE.md 錨點 → design-principles 文件 → guard skill + guardian agent。任何 agent 產出用戶可見內容時自動審查。

### 2. [Token Conservation](./token-conservation/)
Token 節省行為規範。四行制派工格式、一行制回報格式、skill 延遲載入策略、決策權限表、session 狀態摘要。不是 compaction hook（被動），是行為約束（主動）。

### 3. [Non-Engineering Agents](./non-engineering-agents/)
非工程角色 agent 模板。Content Guardian（文案守衛）、Art Director（美術指導）。附設計原則與共通模式說明。

## 快速開始

把你需要的資料夾複製到你的 Claude Code 專案對應目錄下（`skills/`、`agents/`），然後根據各 README 客製化。

## 來自

一個重視設計原則不可妥協的產品專案。在設計文件已佔大量 context 的前提下，這套架構讓 PM agent 自主開發時不偏離產品靈魂，同時把 token 用量壓到可控範圍。

## License

MIT
