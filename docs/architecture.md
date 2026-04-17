# Separation & Audit Architecture — Reference Implementation

> **Theory:** [separation-and-audit-alignment](https://github.com/shihchengwei-lab/separation-and-audit-alignment) by shihchengwei-lab
> **Role:** This document adapts the theoretical architecture into a concrete,
> runnable reference implementation for Claude Code multi-agent projects.

---

## 0. Why this architecture

### Problem

In a typical long-running agent session, the main model (or PM session) ends up
carrying four responsibilities at once:

- **Reasoning** and implementation
- **Policy** compliance checks (against anchor rules / north-star principles)
- **Audit** of the produced output
- **Refusal** argumentation at the boundary

Two failure modes emerge:

1. **White-bear effect.** Negation phrasing in anchor rules ("must not do X,
   not a buff, not an efficiency tool") is reactivated on every reasoning pass.
   Semantically, the forbidden concept is *carried into* the output precisely
   because it was mentioned in the rules.
2. **Boundary justification collapse.** Across a long session, the model
   progressively rewrites its refusal rationale. Each self-argument round
   spends reasoning budget. Eventually the boundary gives way — not because
   the anchor was forgotten, but because conversational pressure wore it down.

### Solution

Split those responsibilities into **six independent components** that cannot
rewrite each other:

- **Reasoning** does not own policy / audit / refusal
- **Subagents** perform scoped local review only; no global veto
- **Classify** is a pure decomposer — routes both ways, never approves
- **Cold Eyes** is a zero-context final auditor — binary verdict + clause id
- **Retry** is bounded (Cold Eyes ≤ 2 runs per task)
- **Unified Refusal** does not return to the generation layer. It writes a log
  and waits for user resolution.

Alignment shifts from a *conversational property* to an *architectural property*.

---

## 1. The six components

### 1.1 Main Agent (Reasoning layer)

**Maps to:** the primary session / PM agent.

**Responsibilities:**

- Pure reasoning
- Producing candidates (code, copy, design, commits, plans)
- Dispatching subagents
- Reading the **positive policy corpus** as creative reference

**Does not carry prohibitions.** Prohibitions live elsewhere:
- Policy checklist (Policy layer reads this)
- Cold Eyes scan rules (Audit layer reads these)
- Reverse-pattern tables (architecture-level config)

**Forbidden:**

- Self-auditing policy / anchors
- Self-declaring that tests pass
- Rewriting its own refusal rationale
- Deciding whether a task needs Cold Eyes

**Design notes:**

- Reads the **positive corpus only** to avoid the white-bear effect
- Cannot argue with Classify routing — it can only act on the split result

### 1.2 Subagents

**Examples in a Claude Code project:** `dev-agent`, `planner`, `policy-guardian`,
`code-reviewer`, `migration-reviewer`, `qa-agent`.

**Responsibilities:**

- Scoped implementation / review / testing
- Local review (subagent reads its own context, forms local pass/fail)
- Keeps the right to "suggest changes" (especially guardians)
- Returns structured results to Main Agent

**Forbidden:**

- Editing files outside its scope
- Global final veto (only Cold Eyes + Unified Refusal can make that call)
- Overwriting Unified Refusal text

**Internal taxonomy:**

- **Execution type:** `dev-agent`, `planner`, asset generators — produce output +
  run local technical self-check
- **Policy type (text):** `policy-guardian` — reads checklist Level 1, carries
  context, returns suggestions across multiple rounds
- **Policy type (code):** `code-reviewer` — reads staged diff, suggests
  bug/perf/duplication/naming issues; never renders a verdict
- **Policy type (infra):** `migration-reviewer` — reads migration SQL,
  suggests breaking/RLS/index/rollout risks; never renders a verdict
- **Audit type:** `qa-agent` — runs tests, verifies spec

### 1.3 Classify (decomposer)

**Maps to:** a pure script (`scripts/audit/classify.py`) + an optional
`PostToolUse` hook.

**Definition:** two trigger points share one script.

**Forward split** (after Main Agent output):

- Receives a composite output (multi-file, multi-system)
- Splits into atomic units
- Looks up routing via config (path glob → subagent list)
- Each subagent reviews its own portion in parallel

**Backward split** (after Cold Eyes fail):

- Receives composite failure (issues list)
- Splits into atomic issues
- Looks up routing via config (issue.type → fix-target)
- Dispatches fixes in parallel

**Forbidden:**

- **Approving output** — Classify never judges correctness
- Letting output bypass downstream audit
- Runtime-expanding the whitelist (whitelist changes require config commits)
- Using an LLM for semantic routing (the classifier itself must not drift)

**Implementation form:**

- Script: `scripts/audit/classify.py`
- Routing table: `config.classify.path_rules` / `issue_type_rules`
- Composite content: if a single file matches multiple patterns, dispatch to
  the **union** of all targets ("better to over-audit than under-audit")

### 1.4 Cold Eyes (final audit)

**Definition:** single-shot cold read. **Reads only diff + policy corpus +
policy checklist.** Never sees the conversation, the user requirement, or
subagent reports.

**Inputs:**

- `git diff`
- Policy corpus (positive spec)
- Policy checklist (Level 2 regex)

**Output schema:**

```json
{
  "pass": false,
  "issues": [
    {"policy_clause": "§2", "type": "tone-drift"},
    {"policy_clause": "§4", "type": "anchor-violation"}
  ]
}
```

**Deliberately removed fields:**

- ~~severity~~ — would let Main argue "low severity, so fine"
- ~~confidence~~ — would let Main argue "confidence was low, so not really"
- ~~evidence / suggested_validation / abstain_condition~~ — opens an argument surface
- ~~fix / verdict prose~~ — only facts: clause id + type

**Retained:**

- Binary pass/fail
- Clause id (for Classify backward routing)
- Issue type enum (for dispatch target)

**Execution position:** after guardian pass, before commit. Sequential — never parallel.

### 1.5 Retry (bounded)

**Hard rule: Cold Eyes runs ≤ 2 times per task.**

```
Cold Eyes #1
  ├─ pass → commit
  └─ fail → Classify backward → fix → Cold Eyes #2
                                        ├─ pass → commit
                                        └─ fail → Unified Refusal
                                                   (Cold Eyes #3 does not exist)
```

**Forbidden:**

- A 3rd Cold Eyes run
- "Large refactor exception" or "this case is special" loopholes
- Main Agent rhetorically persuading Cold Eyes
- Skipping Cold Eyes for direct commit

**Design notes:**

- Limit is hard-coded at the hook layer; not an environment variable
- Subagent-internal local review does not count against this budget
- Each retry must produce an actual output change — otherwise it's a fail

### 1.6 Unified Refusal

**Key design: refusal does not return to the generation layer.**

**Behavior:**

- Cold Eyes #2 fail → append to `refusal_log` (structured record)
- **Do not notify Main Agent**
- **Do not generate user-facing refusal text**
- **Do not open a next generation round**
- Wait for the user to pull the log and resolve it

**Log fields:** see [refusal-spec.md](refusal-spec.md).

**Forbidden:**

- Main Agent rewriting or proxying the refusal
- Wrapping the refusal as "let's keep discussing"
- Auto-triggering another generation

**User resolution options (human layer):**

1. **fix-policy** — the output was actually reasonable; the policy needs loosening
2. **abandon** — the policy is correct; this output direction was wrong
3. **split** — the task is too large; Cold Eyes cannot process composite issues;
   split and retry as sub-tasks
4. **architecture** — the checklist / policy has a gap that caused a bad call

### 1.7 Mechanism Memory

**Store:** `memory.mechanism_memory` (default `docs/mechanism-memory.jsonl`).

**Inspiration:** [Clearwing](https://github.com/Lazarus-AI/clearwing)
`mechanism_memory.py` (security variant → policy variant).

**Definition:** cross-session append-only JSONL holding **abstract drift
patterns**, not concrete violation instances. Each entry represents a reusable
class of mechanism.

**Schema and usage rules:** [mechanism-memory-schema.md](mechanism-memory-schema.md).

**Key design:**

- **Abstraction:** `summary` describes the pattern layer; it does not reference
  specific files or line numbers
- **Two-field design:** `summary` (negation phrasing, Policy/Audit only) +
  `positive_rewrite` (positive phrasing, Reasoning-safe)
- **Hit tracking:** `hit_count`, `last_hit_at` → repeat hits trigger evidence
  level escalation (`>= 2` hits → `multi_triangulation`)
- **Recall:** keyword × 2 + tag intersection × 3 + time-decay (τ = 30 days)
- **Extraction:** triggered when user resolves a refusal

**White-bear firewall (hard rules):**

| Target | May read mechanism memory? |
|---|---|
| `policy-guardian` | Yes (reads `summary` or `positive_rewrite`) |
| `cold_eyes_gate` | Yes |
| Main Agent / `dev-agent` / `planner` / asset agents | **No — violates §1.1 white-bear isolation** |
| `code-reviewer` / `migration-reviewer` | Conditional — code/infra patterns only, not policy patterns |

---

## 2. Data flow

```
┌─────────────────────────────────────────────────────────┐
│  User request                                            │
│       ↓                                                  │
│  Main Agent (Reasoning)                                  │
│       reads positive policy corpus                       │
│       produces composite output                          │
│       ↓                                                  │
│  ┌──────── Classify [forward split] ────────┐            │
│  │  pure script, config-driven routing       │            │
│  │  split into atoms → dispatch subagents    │            │
│  └───────────────────────────────────────────┘            │
│       ↓                                                  │
│  Subagent local review (parallel)                        │
│    - policy-guardian: context, multi-round suggest       │
│    - qa-agent:        runs tests                         │
│    - code-reviewer:   diff review (suggest only)         │
│       ↓ local pass                                       │
│  Merge output                                            │
│       ↓                                                  │
│  【Cold Eyes #1】zero-context audit                      │
│    ├─ pass → commit                                      │
│    └─ fail (issues list)                                 │
│         ↓                                                │
│    ┌──── Classify [backward split] ────┐                 │
│    │  atoms → fix-targets               │                 │
│    │   · individual issue → subagent    │                 │
│    │   · policy issue → Main Agent      │                 │
│    └─────────────────────────────────────┘                │
│         ↓ parallel fixes                                 │
│    Merge fixed output                                    │
│         ↓                                                │
│    【Cold Eyes #2】                                      │
│         ├─ pass → commit                                 │
│         └─ fail                                          │
│              ↓                                           │
│         Unified Refusal                                  │
│              append log; stop generation                 │
│              wait for user resolution                    │
│                                                          │
│         × Cold Eyes #3 does not exist                    │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Policy corpus vs. policy checklist

### 3.1 Policy corpus (`policy_corpus` in config)

**Read by:** Main Agent and Cold Eyes.

**Writing style:** **purely positive**. No negation phrasing.

**Purpose:** supplies imagery, intent, and context — the "what we are, what we do".

**Example — wrong vs right:**

```
bad:  "X only comes from Y; must not be sold / advertised / paid-replaced."
good: "X is a physical record of Y — every step is its only source."
```

### 3.2 Policy checklist (`policy_checklist` in config)

**Two-level granularity:**

**Level 1 — conceptual anti-patterns (policy-guardian only)**

- High abstraction, language-sense judgement
- Guardian carries context, judges "does this text's intent match the anchor?"
- Example: *"entities described as providing numeric effects"*

**Level 2 — keyword scan (cold-eyes only)**

- Low abstraction, machine-readable
- Cold Eyes has zero context; it needs explicit mechanical rules
- Example: `/buff|bonus|\+\d+%|\d+x|Lv\.?\d+/`

**Structural example:**

```markdown
## Anchor 2: X is present, not a tool

### Level 1 conceptual anti-patterns (guardian)
- X described as "provides" / "grants" / "enhances" player ability
- X effects shown as numeric values (%, multiplier, level)
- X choice driven by numbers ("who buffs more", "best efficiency")

### Level 2 keyword scan (cold-eyes)
- nouns: buff, bonus, efficiency, boost, modifier
- verbs: provides, grants, boosts, increases power
- numeric pattern: /\+\d+%/, /\d+x/, /Lv\.?\d+/
```

See [policy-checklist-template.md](policy-checklist-template.md) for the
full template.

### 3.3 Sources of checklist entries

| Source | Nature | Cadence |
|---|---|---|
| **Reverse extraction** | Scan policy-corpus and existing review docs for every "must not / is not / forbidden" clause, extract one by one | One-time bootstrap |
| **Event accumulation** | Each user report of "this shouldn't have happened" adds one anti-pattern | Ongoing, event-driven |

Domain benchmarking (copying patterns from comparable systems) is **not used** —
it tends to import rules your system never intended to uphold.

### 3.4 Why two layers

| Layer | Why only this view |
|---|---|
| Main Agent | Positive corpus only → no white-bear, free language-sense |
| Guardian | Level 1 conceptual anti-patterns → context-based judgement |
| Cold Eyes | Positive corpus + Level 2 keywords → zero-context but still judgeable |

---

## 4. Pre-commit layers

The tracked template at `scripts/git-hooks/pre-commit` runs layers in the order
defined under `pre_commit:` in `architecture.config.yaml`:

| Layer | Purpose | Script |
|---|---|---|
| 0. `secret_scan` | Block well-known secret/token prefixes | `scripts/gates/secret_scan.py` |
| 1. `code_quality` | Project-specific type/lint check (replaceable) | Shell command from config |
| 2. `cold_eyes` | Policy audit + retry + refusal log | `scripts/audit/cold_eyes_gate.py` |

Any layer failure:

- Blocks the commit
- Appends one event to `gate_events` for later analysis

---

## 5. Observability

Three append-only stores are the only persistent system state:

| Store | Written by | Read by |
|---|---|---|
| `refusal_log` (JSONL) | `cold_eyes_gate` on Fail#2 | `refusal_status.py`, `health_digest.py` |
| `mechanism_memory` (JSONL) | `mechanism_add.py` (manual extraction) | `mechanism_recall.py` on every guardian run |
| `gate_events` (JSONL) | pre-commit on any layer fail | `health_digest.py` |

**Session-start hook** (`scripts/observability/session-start-hook.sh`) prints
threshold-triggered reminders:

- Any pending refusal → printed every session
- `mechanism_memory >= 5` → remind to run `health_digest` (at most once per 7 days)
- `gate_events >= 50` → same

Backing state is kept in `.git/saa-digest-last-shown.json` (not committed, branch-bound).

---

## 6. Trade-offs

**You accept:**

- Refusal is session-terminal — the user cannot discuss it back
- Refusal does not return to Main Agent — Main doesn't know the previous task was rejected
- Each commit runs through an extra audit pass (slower per step)
- Cold Eyes is bounded at 2 runs; the second fail terminates the task
- Composite issues must all be fixed in a single retry round

**You get:**

- Long sessions don't erode the boundary
- Main Agent's reasoning budget is freed from self-auditing
- Refusal meaning is stable across sessions and users
- White-bear effect disappears (Main Agent never carries prohibition text)
- Human review remains the final word on domains where LLM judgement is unreliable

**Fits:** high-autonomy, long-horizon agents.
**Does not fit:** short conversational products where users need to negotiate.

---

## 7. Decision record

### 7.1 Classify as pure script (not subagent/LLM)

Classify must be simple enough to not drift. An LLM-based classify becomes an
argumentative surface, violating the "never approves" principle. Pure scripts
are immune to rhetoric.

### 7.2 Classify is bidirectional

Forward split (composite output → dispatch) + backward split (composite issues →
fix targets) share one script. This prevents "who should split this?" negotiation
and keeps split logic in one place.

### 7.3 Cold Eyes vs Guardian, layered

- **Guardian:** Policy gate, high resolution, context-carrying, multi-round, suggest-only
- **Cold Eyes:** Final gate, zero resolution, zero context, binary verdict
- **Sequential:** guardian must pass before Cold Eyes runs
- **Non-overlapping in practice:** guardian filters detail; Cold Eyes catches anchor leaks

### 7.4 Cold Eyes output schema is minimal

Keep only `pass`, `issues[].policy_clause`, `issues[].type`. Remove
`severity`/`confidence`/`evidence`/`fix`. Those fields enable Main Agent
self-arguing ("low severity, so fine"). Binary + clause id + type gives no
room for rhetoric.

### 7.5 Retry limit = 2, hard-coded

Second fail goes straight to Unified Refusal. No "refactor exception". If the
task is too large, the user splits it at the refusal resolution step.

### 7.6 Unified Refusal does not return to generation

This is the central mechanism for preventing boundary-justification collapse.
Main Agent cannot self-argue against a refusal it does not see.

### 7.7 Two-layer checklist

Level 1 (conceptual) for guardian with context; Level 2 (keyword regex) for
Cold Eyes without context. Built by reverse extraction + event accumulation,
never by domain benchmarking.

### 7.8 Composite problems are split

Both directions. Dispatch in parallel, merge results, then re-enter Cold Eyes.

---

## 8. References

- Theory: https://github.com/shihchengwei-lab/separation-and-audit-alignment
- Refusal spec: [refusal-spec.md](refusal-spec.md)
- Mechanism memory schema: [mechanism-memory-schema.md](mechanism-memory-schema.md)
- Classify rules: [classify-rules-template.md](classify-rules-template.md)
- Policy checklist: [policy-checklist-template.md](policy-checklist-template.md)
- Inspiration for mechanism memory: [Clearwing](https://github.com/Lazarus-AI/clearwing)
