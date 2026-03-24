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

1. 把你需要的資料夾複製到你的 Claude Code 專案對應目錄下：
   ```bash
   # 例：使用 Design Integrity Guard
   cp -r design-integrity-guard/skills/ your-project/.claude/skills/
   cp -r design-integrity-guard/agents/ your-project/.claude/agents/
   ```
2. 根據各子目錄的 README 客製化設定
3. 在你的 `CLAUDE.md` 中加入對 design-principles 的引用（詳見 [design-integrity-guard/README](./design-integrity-guard/README.md)）

每個組件可以獨立使用，也可以組合搭配。

## 適合誰

- 用 Claude Code multi-agent 架構做產品開發，但發現 agent 越跑越偏離設計方向的人
- 想讓非工程角色（文案、美術）也能被 agent 工作流管理的團隊
- 在 context window 吃緊的情況下，需要主動省 token 策略的專案

## 來自

來自實際產品開發中的踩坑經驗。當 agent 足夠自主，它會在你不注意的時候把精心設計的文案改得面目全非、把統一的視覺語言搞得四分五裂。這套工具就是為了解決這個問題而生的。

## License

MIT
