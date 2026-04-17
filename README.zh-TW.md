# Separation & Audit — Claude Code 參考實作

> 🌐 **語言：** [English](README.md) · 繁體中文（本檔）

**[separation-and-audit-alignment](https://github.com/shihchengwei-lab/separation-and-audit-alignment) 架構在 Claude Code multi-agent 專案上的可執行參考實作。**

> Alignment 從「對話屬性」變成「架構屬性」。
>
> — 來自理論 repo

與其讓同一個模型同時承擔推理、自我監控、與拒絕權威，這個 repo 把這些職責拆成
**獨立的 pipeline 層**，彼此之間沒有論辯介面。結果：長 session 下邊界不被磨損，
拒絕變成冷資料而非可協商事件。

這是 `claude-code-creative-toolkit` v2.0。v1 toolkit 保留在
[`examples/creative-writing/`](examples/creative-writing/) 作為領域範例。

---

## 這個 repo 給你什麼

六個 component，每個都是具體檔案或 script：

| 層 | Component | 位置 |
|---|---|---|
| Reasoning | Main Agent | 你的 PM / 主 Claude Code session |
| Policy（文字） | `policy-guardian` | [`agents/policy-guardian.md`](agents/policy-guardian.md) |
| Policy（程式碼） | `code-reviewer` | [`agents/code-reviewer.md`](agents/code-reviewer.md) |
| Policy（infra） | `migration-reviewer` | [`agents/migration-reviewer.md`](agents/migration-reviewer.md) |
| Classify（分解器） | `scripts/audit/classify.py` | config 驅動路由 |
| Audit（Cold Eyes） | `scripts/audit/cold_eyes.py` + `cold_eyes_gate.py` | pre-commit 層 |
| Memory（跨 session） | `scripts/memory/mechanism_*.py` | mechanism memory + refusal log |
| Gates | `scripts/gates/secret_scan.py` + pre-commit 模板 | 可配置的 layers |
| Observability | `scripts/observability/health_digest.py` + session-start hook | 超閾值主動提醒 |

全部由一份檔案驅動：[`config/architecture.config.example.yaml`](config/architecture.config.example.yaml)。

---

## 快速開始

```bash
# 1. Clone 這個 repo，放進你的專案 root 或旁邊
git clone https://github.com/shihchengwei-lab/separation-and-audit-claude-code

# 2. 安裝唯一的執行時依賴（PyYAML，用來 parse config）
pip install -r requirements.txt

# 3. 把範例 config 複製到你的專案 root
cp config/architecture.config.example.yaml architecture.config.yaml

# 4. 指向你自己的 policy corpus 與 policy checklist
#    （這兩份檔案由你寫 — 格式見 docs/policy-checklist-template.md）

# 5. 裝 pre-commit hook 模板
cp scripts/git-hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# 6. 在 Claude Code settings 註冊 session-start hook
#    JSON 範例見 docs/refusal-spec.md §6.1
```

然後把 `agents/*.md` 複製到你的專案 `.claude/agents/` 目錄，透過
Claude Code 正常的 subagent 流程派工即可。

---

## Pipeline 流程

```
使用者請求
     ↓
Main Agent（Reasoning）  — 只讀正面 policy corpus
     ↓
Classify [forward split]  — 純 script，config 驅動路由
     ↓
Subagents（policy-guardian / code-reviewer / qa-agent / ...） — 本地審查
     ↓
【Cold Eyes #1】  — 零 context 對照 policy checklist Level 2
     ├─ pass → commit
     └─ fail → Classify [backward split] → 修正 → 【Cold Eyes #2】
                                                    ├─ pass → commit
                                                    └─ fail → Unified Refusal
                                                               （寫 log；停止；等 User 裁決）
```

完整架構推理：[`docs/architecture.md`](docs/architecture.md)。

---

## 關鍵設計

**白熊絕緣（White-bear isolation）。** 否定句形式的禁令不進 Reasoning 層。
Main Agent 只讀正面 policy；Policy 層讀否定版；Reasoning 永不觸發
「別想白熊」這種反效果。

**零 context Cold Eyes。** 最終稽核只看 diff + policy — 不看對話、不看需求、
不看 subagent 回報。徹底移除「可被論辯說服而放寬」的所有介面。

**有界 retry + 沉默拒絕。** Cold Eyes 最多跑兩次。第二次 fail 寫結構化
refusal log，而且**不回傳到生成層** — Main Agent 根本不知道拒絕發生過。
User 透過 session-start hook 或 CLI 發現 pending refusal，離線裁決。

**Mechanism memory，雙欄位設計。** 跨 session 的 drift-pattern 記憶，
硬性白熊防線：否定式的 `summary` 只注入 Policy / Audit 層；正面版的
`positive_rewrite` 是唯一可給 Reasoning 層讀的欄位。

**Config 優於慣例。** 幾乎所有路徑、regex、層級、規則都在一份
`architecture.config.yaml`。在新專案重新裝模板、指向你的 corpus，
整條 pipeline 就能跑。

---

## 文件

- [`docs/architecture.md`](docs/architecture.md) — 六 component 完整規格
- [`docs/refusal-spec.md`](docs/refusal-spec.md) — Unified Refusal 模組
- [`docs/mechanism-memory-schema.md`](docs/mechanism-memory-schema.md) — 記憶層
- [`docs/policy-checklist-template.md`](docs/policy-checklist-template.md) — checklist 格式
- [`docs/classify-rules-template.md`](docs/classify-rules-template.md) — Classify 路由

## 範例

- [`examples/creative-writing/`](examples/creative-writing/) — 原 v1.x toolkit，
  保留為領域範例。展示通用架構如何映射到內容／創作型工作。

---

## 與理論 repo 的關係

本 repo 是 [shihchengwei-lab/separation-and-audit-alignment](https://github.com/shihchengwei-lab/separation-and-audit-alignment)
所提出架構的**參考實作**。

- 理論 repo（CC BY 4.0）記錄長 LLM session 下觀察到的 alignment
  distortion pattern，論證 pipeline 層級的 authority 分離
- 本 repo（MIT）把該 pipeline 具體實作給 Claude Code 使用

若引用理論，請引理論 repo；若 fork 實作，本 repo 的 MIT license 適用。

---

## 這個 repo **不是**

- **不是現成的 prompt pack。** policy corpus 與 checklist 你自己寫；
  這個 repo 提供執行的 pipeline。
- **不是測試套件的替代。** Cold Eyes 在 diff 上稽核 policy 合規，不取代你的
  test suite。請搭配專案 CI 使用。
- **不適合短對話產品。** Unified Refusal 設計上是 session 終局的 —
  適合自主代理，不適合使用者需要協商的 chatbot 場景。

---

## 狀態

v2.0（2026-04-18）— 改名後的首個 release。
若你原本用 v1.x `claude-code-creative-toolkit`，遷移說明在
[`examples/creative-writing/README.md`](examples/creative-writing/README.md)。

## License

MIT。見 [LICENSE](LICENSE)。
