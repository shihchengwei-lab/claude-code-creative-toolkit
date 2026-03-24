# Non-Engineering Agent Templates

**Claude Code 不只能寫 code。這些 agent 模板讓你的 PM 也能管創意產出。**

開源社群的 Claude Code agent 幾乎全是工程角色（code-reviewer、security-auditor、test-automator）。但很多產品需要非工程角色：文案、美術、品牌、翻譯、法規。這組模板填補這個空白。

## 模板一覽

### content-guardian（文案守衛）
**適用：** 任何需要文案品管的產品——遊戲對話、app 文案、品牌內容、教育教材

核心設計：
- 雙重角色：寫 + 審，但審查時獨立於撰寫，不預設正確
- 搭配 design-integrity-guard skill 運作
- PM 自動觸發審查，不需 user 介入

### art-director（美術指導）
**適用：** 任何用 AI 生圖的專案——遊戲美術、行銷素材、產品插圖

核心設計：
- 不直接生圖，而是產出 prompt spec + 風格規格文件
- 維護全專案視覺一致性
- 所有美術產出須經 user 最終審核（AI 生圖品質不穩定，不能全自主）

### translator-localizer（翻譯在地化）— 建議新增
**原始專案沒有，但模式一樣。** 適用：多語系產品

核心設計：
- 翻譯時載入 design-integrity-guard，確保翻譯後語氣不走味
- 在地化判準：不是逐字翻，是「這個文化的人讀起來感受一樣嗎」
- 禁用詞彙表需要每個語系各一份

---

## 非工程 Agent 的共通設計原則

從實戰經驗提煉出來的：

### 1. 產出必須經 user 審核
工程 agent 可以靠測試自動驗收，非工程 agent 的產出品質是主觀的。規則：agent 自檢 → PM 初篩 → user 最終審核。

### 2. 守衛角色獨立於創作角色
寫跟審是兩個心態。即使是同一個 agent，審查模式下要重新載入判準，不帶著「我寫的應該沒問題」的預設。

### 3. 用 skill 而非 agent prompt 承載判準
判準會迭代、會更新。放在 skill 裡可以獨立修改，不需要每次都改 agent 定義。

### 4. model 選擇比工程 agent 更重要
文案品質對模型能力高度敏感。guardian 類 agent 建議用 Opus，執行類（照規格生圖 prompt）可以用 Sonnet。

---

## 怎麼用

1. 複製你需要的 agent 模板到專案的 `agents/` 資料夾
2. 根據你的產品修改職責和規則
3. 搭配 design-integrity-guard plugin 使用效果最好
4. 在 PM 的派工邏輯中加入自動觸發條件

## 來自

提煉自一個所有文案和美術都不能背叛產品精神方向的實際專案。
