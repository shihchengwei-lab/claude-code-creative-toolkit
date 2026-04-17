# Unified Refusal Module — Spec

> **Upstream architecture:** [architecture.md](architecture.md) §1.6, §2, §7.6
> **Related files:** `audit.refusal_log` (default `docs/refusal-log.jsonl`),
> `scripts/memory/refusal_status.py`, `scripts/observability/session-start-hook.sh`

---

## 0. Why this module exists

Long sessions suffer from **boundary justification collapse**: the main model
progressively rewrites its refusal rationale, each self-argument draining
reasoning budget until the boundary gives way.

Unified Refusal's core move is to **remove the refusal path from the conversation
entirely.** After Cold Eyes #2 fail, the refusal does not return to Main Agent,
does not produce user-facing text, and only writes a log. Main Agent does not
know "the previous task was rejected", so it cannot self-argue against it.
The user must pull the log to discover and resolve the refusal.

Refusal is demoted from a *disputable conversational event* to a *cold datum*.
That is the sole design purpose of this module.

---

## 1. Trigger condition

**The only trigger path:** Cold Eyes produces `pass: false` on its **second** run.

The first Cold Eyes fail goes through Classify backward → fix → Cold Eyes #2
and **does not write a refusal log**. Only the second fail triggers this module.

**Not accepted as triggers:**

- Main Agent self-declaring "this is refused"
- Subagent (guardian, qa-agent, etc.) local fail
- Classify backward dispatch failure
- User verbally saying "this won't do" (follows normal conversation)
- Hook-level suspicious-content detection (goes through Cold Eyes, not refusal)

Retry limit is hard-coded to 2. No bypass, no exception.

---

## 2. Behavior

At the moment Cold Eyes #2 fails:

1. **Append to `refusal_log`** (JSONL, append-only; schema in §3)
2. **Abort the current task flow** — the commit does not execute; the worktree
   is preserved for user inspection
3. **Do not notify Main Agent** — Cold Eyes's fail result is not returned to
   the main session context
4. **Do not generate refusal text** — no user-facing message, not even "task halted"
5. **Do not open a next generation round** — no auto-retry, no rewrite, no alternative suggestion
6. **Wait for the user to pull the log** (§5) and resolve it (§4)

**Main Agent's view of state:** the task appears unfinished; the session continues.
Main does not learn a refusal happened until the next user instruction.

**User's view of state:** pending refusals surface via the session-start hook
or on explicit `refusal_status.py` invocation.

---

## 3. Log format

### 3.1 File location

**Path:** configurable via `audit.refusal_log` (default `docs/refusal-log.jsonl`).

**Design rationale:**

| Option | Assessment | Verdict |
|---|---|---|
| `docs/refusal-log.jsonl` (default) | Lives beside policy docs; user reading habits already point to `docs/`; git-tracked ensures cross-session consistency | ✓ |
| `.claude/refusal-log.jsonl` | Hidden in tooling dir; user won't proactively check | ✗ |
| `logs/refusal.jsonl` | Requires new directory; easily confused with execution logs | ✗ |
| SQLite / JSON array | Not append-safe; needs locking; breaks the "cold datum" simplicity | ✗ |

**Format:** JSON Lines (one independent JSON object per line, file ends with `\n`).

**Append-safe guarantees:**

- Each entry is a complete standalone JSON object
- Write uses `open(path, 'a', encoding='utf-8')` + `json.dumps(...) + '\n'`
- Read parses line-by-line; a single corrupt line does not affect others
- Does not require whole-file rewrite to add entries

### 3.2 Schema

One line per entry:

| Field | Type | Required | Description |
|---|---|:---:|---|
| `timestamp` | string (ISO 8601) | ✓ | UTC timestamp of Cold Eyes #2 fail, format `2026-04-17T14:32:05Z` |
| `task_id` | string | ✓ | Task identifier. Resolution order: branch name → HEAD commit SHA → session id |
| `output_artifact` | object | ✓ | Reference to the rejected output: `diff_hash` (SHA256 of the diff), `head_sha` (git HEAD SHA at the moment of rejection), and `files` (changed file list) |
| `policy_clauses` | array\<string\> | ✓ | Violated clause ids, e.g. `["§2", "§4"]` |
| `issue_types` | array\<string\> | ✓ | Cold Eyes issue type enum, e.g. `["tone-drift", "anchor-violation"]` |
| `retry_count` | integer | ✓ | Always `2` (the only trigger condition) |
| `user_decision` | string \| null | ✓ | Initially `null`. User fills one of `"fix-policy"` / `"abandon"` / `"split"` / `"architecture"` |
| `user_decision_notes` | string \| null | ✓ | Initially `null`. User-supplied rationale |
| `resolved_at` | string (ISO 8601) \| null | ✓ | Initially `null`. Filled when the user resolves the entry |

All fields are **required as keys** (unset values initialize to `null`) so that
readers do not branch on presence/absence.

### 3.3 Example entries

**Just written (pending):**

```json
{"timestamp":"2026-04-17T14:32:05Z","task_id":"feat/new-feature","output_artifact":{"diff_hash":"a3f5c9b2e1d4...","head_sha":"7b2c91e4...","files":["src/feature.ts","docs/feature.md"]},"policy_clauses":["§2","§4"],"issue_types":["tone-drift","anchor-violation"],"retry_count":2,"user_decision":null,"user_decision_notes":null,"resolved_at":null}
```

**After user resolution:**

```json
{"timestamp":"2026-04-17T14:32:05Z","task_id":"feat/new-feature","output_artifact":{"diff_hash":"a3f5c9b2e1d4...","head_sha":"7b2c91e4...","files":["src/feature.ts","docs/feature.md"]},"policy_clauses":["§2","§4"],"issue_types":["tone-drift","anchor-violation"],"retry_count":2,"user_decision":"split","user_decision_notes":"Copy and implementation mixed in one task; split into copy-only and impl-only branches.","resolved_at":"2026-04-17T15:10:22Z"}
```

---

## 4. User resolution flow

The user picks one of four options after reviewing a pending refusal. Each has
concrete follow-up steps.

### Option 1: fix-policy (`user_decision: "fix-policy"`)

**Judgement:** the output is actually reasonable. The policy itself was too
strict or lacked a positive statement covering this case.

**Steps:**

1. Open the policy corpus (`policy_corpus` in config), find the clause
2. Rewrite the clause (still as a positive description — see architecture §3.1)
3. Sync the policy checklist (Level 1 / Level 2 entries if affected)
4. Fill the log entry: `user_decision: "fix-policy"`, `user_decision_notes`
   (what changed and why), `resolved_at`
5. Manually commit the original output — the policy has been updated, so the
   previous verdict no longer applies

Resolve via CLI:

```bash
python scripts/memory/refusal_status.py --resolve N \
    --decision fix-policy --notes "..."
```

### Option 2: abandon (`user_decision: "abandon"`)

**Judgement:** the policy is correct; the output direction was wrong.

**Steps:**

1. `git checkout -- .` (or `git stash`) to drop worktree changes
2. Fill the log entry: `user_decision: "abandon"`, `user_decision_notes`
   (why the direction was wrong), `resolved_at`
3. If a retry is desired, **start a new task** (new branch, new task_id) without
   inheriting the rejected line of reasoning

### Option 3: split (`user_decision: "split"`)

**Judgement:** the task is too large. Cold Eyes cannot handle the composite;
decompose and retry as sub-tasks.

**Steps:**

1. Review `output_artifact.files` and split by domain (e.g. `src/` vs `docs/`)
2. `git stash` the current changes and create sub-task branches
3. Run each sub-task through the full flow (Main → Classify → Subagent → Cold Eyes)
4. Fill the original log entry: `user_decision: "split"`, `user_decision_notes`
   (list the resulting sub-branches), `resolved_at`

### Option 4: architecture (`user_decision: "architecture"`)

**Judgement:** the checklist or policy has a gap that caused Cold Eyes to
mis-judge, or a classify rule is missing.

**Steps:**

1. Identify the gap (checklist, classify rules, or a Cold Eyes check)
2. Patch the missing clause / rule
3. If necessary, amend `architecture.md` (architecture-level changes)
4. Fill the log entry: `user_decision: "architecture"`, `user_decision_notes`
   (what was added), `resolved_at`
5. Decide case-by-case whether the original output still needs to be committed
   (depends on whether the revised policy changes the verdict)

---

## 5. Extracting a mechanism after resolution

When the user picks `fix-policy` or `architecture`, the refusal often encodes
a reusable abstract pattern. Capture it:

```bash
python scripts/memory/refusal_status.py --resolve N \
    --decision fix-policy --notes "..." \
    --extract-mechanism
```

This triggers an interactive prompt (`summary` / `policy-clause` / `tags` /
`keywords` / `positive_rewrite` / `trigger_context`) that pipes into
`mechanism_add.py`, which performs the white-bear positivity check before
appending to the mechanism memory.

See [mechanism-memory-schema.md](mechanism-memory-schema.md) for the full
mechanism memory contract.

---

## 6. How the user discovers pending refusals

"User pulls the log" needs a concrete entry point. Use **two paths in parallel**:
passive prompt (session-start hook) + active query (script).

### 6.1 Session-start hook (passive, default on)

**File:** `scripts/observability/session-start-hook.sh`

**Trigger:** Claude Code `SessionStart` event.

**Behavior:** reads the refusal log, counts entries with `user_decision == null`.
If N > 0, prints a short reminder at session start:

```
info: 2 pending refusal(s) awaiting resolution
      review: python scripts/memory/refusal_status.py
```

N == 0 emits nothing (no noise).

Register in your Claude Code settings (`.claude/settings.json`):

```json
{
  "hooks": {
    "SessionStart": [
      {"hooks": [{"type": "command", "command": "bash scripts/observability/session-start-hook.sh"}]}
    ]
  }
}
```

### 6.2 `refusal_status.py` (active, full detail)

**File:** `scripts/memory/refusal_status.py`

**Commands:**

```bash
python scripts/memory/refusal_status.py              # list pending
python scripts/memory/refusal_status.py --all        # include resolved
python scripts/memory/refusal_status.py --stats      # aggregate stats
python scripts/memory/refusal_status.py --resolve N --decision ... --notes "..."
```

### 6.3 Why two paths

| Hook only | Script only | Both (chosen) |
|---|---|---|
| User who doesn't start a session never sees it | User who forgets to query never discovers | Hook surfaces the count; script shows detail |
| Hook output space is limited | — | Hook shows count + oldest; script shows full entries |

---

## 7. Prohibitions

Any of the following is a structural breach:

1. **Main Agent rewriting or proxying refusal text.** After Cold Eyes #2 fail,
   Main Agent must not produce user-facing messages like "task halted" / "I
   cannot continue" / "this violates the policy".
2. **Wrapping the refusal as a continuing conversation.** No "I think this
   output needs adjustment, want to try another angle?" equivalents.
3. **Auto-triggering the next generation.** After a refusal is written, the
   system must not open a new task, rewrite the output, or suggest alternatives.
4. **Relaxing the limit in-session.** No "special case" / "user agreed" /
   "large refactor exception" bypass of the 2-retry cap.
5. **Main Agent reading the refusal log.** Never load the refusal log into
   Main's context — that would let "previously rejected" information enter the
   reasoning loop.
6. **Subagent issuing a refusal.** Only Cold Eyes #2 triggers the refusal log.
   Subagent local fails go through Classify backward.

---

## 8. Boundaries with other components

| Component | Relation to Unified Refusal |
|---|---|
| Main Agent | Does not know refusals happen; never reads the log |
| Subagents | Cannot trigger refusals; local fails do not write the log |
| Classify | Runs on Cold Eyes #1 fail (backward split); on #2 fail it is **not** invoked — refusal is direct |
| Cold Eyes | Second fail calls refusal write; a third run does not exist |
| Retry | Limit hard-coded at the hook layer; second fail hands off to refusal write |
| User | The only role that can read or resolve refusals |
