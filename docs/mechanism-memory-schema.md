# Mechanism Memory — Schema & SOP

> **Store:** `memory.mechanism_memory` (default `docs/mechanism-memory.jsonl`), append-only JSONL
> **Inspiration:** [Clearwing](https://github.com/Lazarus-AI/clearwing) `mechanism_memory.py` (security variant → policy variant)
> **Architecture position:** [architecture.md](architecture.md) §1.7

---

## 1. Why this exists

The policy checklist is a **static rule table** (Level 1 conceptual anti-patterns
+ Level 2 regex). But **every violation is a concrete instance of a pattern** —
different surface shape, same underlying mechanism.

Problems without mechanism memory:

- Every guardian review starts from scratch, reading corpus + checklist with no history
- The same class of violation appears repeatedly without accumulation
- User insights from past refusal resolutions live in the chat only; next session starts cold

**Mechanism memory = abstracting concrete violations into patterns, persisted
across sessions, so the Policy layer can recall relevant history on every review.**

---

## 2. Schema

One line per JSON entry:

```json
{
  "id": "uuid-v4",
  "created_at": "2026-04-18T12:34:56Z",
  "summary": "<abstract pattern description — not a concrete bug report>",
  "policy_clause": "§1..§N / deathline",
  "tags": ["tag1", "tag2", "..."],
  "keywords": ["term1", "term2", "..."],
  "trigger_context": "what context produces this pattern",
  "positive_rewrite": "<positive version injected into Reasoning-safe contexts>",
  "source_refusal_id": "<refusal-log timestamp> | null",
  "source_commit": "<git SHA> | null",
  "hit_count": 1,
  "last_hit_at": "2026-04-18T12:34:56Z",
  "user_resolution": "<what the user did after resolving the refusal>"
}
```

### Field contract

| Field | Rules |
|---|---|
| `id` | UUID v4, generated at extraction |
| `created_at` | ISO-8601 UTC, extraction time |
| `summary` | **Abstract description** (pattern layer); no specific file / line number |
| `policy_clause` | `§1`, `§2`, …, or `deathline`. For multi-clause violations pick the primary one |
| `tags` | 3–6 tags in snake_case (English) for grouping/filtering |
| `keywords` | Words or phrases (any language) used by recall's substring match |
| `trigger_context` | One sentence: "when does this pattern emerge" |
| `positive_rewrite` | **White-bear firewall** — positive rephrasing (see §4) |
| `source_refusal_id` | Originating refusal entry (if any) |
| `source_commit` | Git SHA of the triggering commit (if any) |
| `hit_count` | `+1` on every recall hit; `>= 2` qualifies for evidence level `multi_triangulation` |
| `last_hit_at` | Updated on every recall hit |
| `user_resolution` | How the user resolved the originating refusal (e.g. "policy corpus §2 gained a positive counter-clause") |

---

## 3. Evidence Level Taxonomy

Guardian output must carry an **evidence level** (5 levels, weakest to strongest):

| Level | Definition | What it points to |
|---|---|---|
| `suspicion` | Language-sense discomfort, no concrete citation | (no corpus reference) |
| `corpus_text_hint` | Corpus has a related section, not a direct conflict (indirect implication) | `corpus.md §X Lyy-zz` |
| `corpus_direct_conflict` | Corpus has an explicit opposing clause | `corpus.md §X Lyy-zz` + quoted text |
| `multi_triangulation` | Multiple corpus clauses or mechanism memory entries converge (`hit_count >= 2`) | Multiple refs + mechanism ids |
| `field_validated` | Real-world usage / user feedback has confirmed this pattern's negative effect | Feedback report reference |

### Rules of use

- **`suspicion` is not a pass grade** — all levels are flags, to be weighed by the user or dev-agent
- **Guardian must always emit a level** — missing it → PM returns the review as incomplete
- **No level-skipping** — on one review, report one level, pick the strongest one you can justify
- **Escalation triggers:**
  - `suspicion` → `corpus_text_hint`: found a related corpus section
  - `corpus_text_hint` → `corpus_direct_conflict`: can quote an opposing clause
  - `corpus_direct_conflict` → `multi_triangulation`: mechanism memory hit with `hit_count >= 2`, **or** multiple corpus clauses converge
  - `multi_triangulation` → `field_validated`: corresponding entry in a feedback-report / `user_decision=fix-policy` history

### `field_validated` backflow

A user's field report / feedback → filed in your feedback report → if it matches
an existing mechanism pattern, annotate that mechanism's `user_resolution` with
a `field-confirmed: <report reference>` note. Subsequent recalls can then mark
the hit as `field_validated`.

---

## 4. White-bear firewall (core safety boundary)

The `summary` field is **negation phrasing** (describing the violation pattern).
Injecting it into Reasoning-layer agents **activates the white-bear effect**.

### Injection rules (hard)

| Target | Can read mechanism memory? | Reason |
|---|---|---|
| `policy-guardian` | Yes | Policy layer; already reads checklist Level 1 negations |
| `cold_eyes_gate` | Yes | Machine layer; no cognitive budget to spend |
| **Main Agent (PM / primary session)** | **No** | Violates architecture §1.1 "positive corpus only" |
| **`dev-agent`** | **No** | Reasoning type |
| **`planner`** | **No** | Reasoning type |
| **asset / creative agents** | **No** | Reasoning type |
| `code-reviewer` | Conditional | May read code-level patterns only; never policy patterns |
| `migration-reviewer` | Conditional | Same as above |

### What `positive_rewrite` is for

If mechanism insight needs to flow back into a Reasoning-layer agent (e.g. briefing
a dev-agent before implementation), **inject `positive_rewrite` only, never `summary`.**

**Example:**

- `summary` (negation): *"Entity dialogue drifts when anachronistic vocabulary appears"*
- `positive_rewrite` (positive): *"Entity dialogue preserves its period-appropriate register"*

### White-bear positivity self-check

On extraction, `positive_rewrite` must pass this check before entering the store:

- **Must not contain** negation particles:
  - Chinese: 不要 / 不可 / 不得 / 不能 / 避免 / 禁止 / 而非 / 而不是 / 不是 / 勿
  - English: don't / doesn't / do not / shouldn't / must not / avoid / prohibit / forbid / rather than / instead of / the standalone word "not"
- **Must be phrased as a positive assertion**: what to do (positive verb),
  what something is (positive predicate)

`scripts/memory/mechanism_add.py` enforces this check automatically.
On failure, the entry is rejected and the user rewrites.

---

## 5. Recall mechanism

`scripts/memory/mechanism_recall.py` (keyword + tag overlap):

### Input

- `--text "<content under review>"` — guardian's current text
- `--tags tag1,tag2` (optional) — expected tags
- `--top-n N` (default 3) — return top N

### Scoring

For each mechanism:

- Keyword substring hits in `--text`: **×2 each**
- Tag intersection with `--tags`: **×3 each**
- `last_hit_at` exponential decay (τ = 30 days, configurable): multiplier in `[0.5, 1.0]`
- Sort by total, take top N with `score > 0`

### Output

```json
[
  {
    "id": "...",
    "summary": "...",
    "positive_rewrite": "...",
    "policy_clause": "§2",
    "hit_count": 3,
    "score": 12.5
  }
]
```

### Side effect on hit

- Each returned entry: `hit_count += 1`, `last_hit_at = now`
- These fields are **in-place updated** (the whole JSONL is rewritten)
- Rewrite uses atomic write (`.tmp` → rename) to survive interruption

---

## 6. Extraction flow

### 6.1 When to extract

When the user resolves a refusal as `fix-policy` or `architecture` and the
case encodes a **reusable abstract pattern**, run:

```bash
python scripts/memory/refusal_status.py --resolve N \
  --decision fix-policy --notes "..." \
  --extract-mechanism
```

### 6.2 Extraction steps (manual + optional LLM assist)

**Step 1 — Gather material:**

- Read the refusal log entry (diff_hash, policy_clauses, files)
- Read the diff of the corresponding commit (the violating content)
- Read the user's `--notes` (resolution rationale)

**Step 2 — Compose the fields:**

- `summary` / `tags` / `keywords` / `trigger_context` / `positive_rewrite`
- Keep `summary` abstract; keep `positive_rewrite` free of negation

**Step 3 — White-bear self-check:**

- `positive_rewrite` is validated against negation tokens
- If it fails, the extraction is rejected; user rewrites

**Step 4 — Append:**

- Generate UUID v4
- Atomic append to `memory.mechanism_memory`
- Optional: update the refusal entry's `user_resolution` to include the mechanism id

---

## 7. Guardian integration

### Prompt injection placement

Before dispatching `policy-guardian`, the PM runs recall:

```bash
python scripts/memory/mechanism_recall.py --text "<text under review>" --top-n 3
```

The returned top-N mechanisms attach as an **independent block** at the end
of the guardian prompt:

```
---
## Historical mechanism recall (top 3)

These are patterns this class of content has tripped on before.
When emitting your evidence level, check against these first:

1. [id=xxx, hits=3, §2] Entity dialogue drifts when anachronistic vocabulary appears
   Positive rephrase: Entity dialogue preserves its period-appropriate register
   Last hit: 2026-03-15

2. [id=yyy, hits=1, §4] ...
```

### Guardian output format

Guardian must respond with this schema:

```markdown
## Guardian review

**Evidence Level**: <suspicion | corpus_text_hint | corpus_direct_conflict | multi_triangulation | field_validated>

**Corpus citation**:
- <if level >= corpus_text_hint, quote corpus §X Lyy-zz>

**Mechanism hits**:
- <if recall hit, list mechanism ids>

**Violation pattern**:
- <concrete summary of the current output's issue>

**Suggested revision**:
- <positive rephrasing — write "change to Y", not "don't do X">
```

### Fail case: evidence insufficient

If guardian can only reach `suspicion`:

- It does **not** pass and does **not** reject
- It reports: "only suspicion-level; recommend user decision on whether to pass"
- User decides whether to promote the case into a new corpus clause or a first mechanism entry

---

## 8. Evidence level ↔ mechanism memory interaction

These are **two views of the same pipeline:**

```
New violation appears
  ↓
Guardian reviews → emits evidence level
  ↓
hit_count >= 2 mechanism hit → auto-escalates to multi_triangulation
  ↓
User resolves refusal → may trigger mechanism extraction → append
  ↓
Next similar violation → recall matches more easily → evidence level reaches higher faster
  ↓
Long term: a mechanism whose hit_count spikes → the underlying policy clause
  may be under-specified → user decides whether to strengthen the architecture
```

---

## 9. Implementation status

Out of the box in this reference implementation:

- `scripts/memory/mechanism_recall.py` — scoring + atomic update
- `scripts/memory/mechanism_add.py` — manual extraction CLI + white-bear check
- `scripts/memory/refusal_status.py --extract-mechanism` — integrated interactive flow
- White-bear firewall rules (summary vs positive_rewrite dual-field design)

Optional add-ons (implement when the pain emerges):

- `mechanism_extract.py` — LLM-assisted extraction (current interactive prompt covers most cases)
- `field_validated` backflow automation (currently manual annotation)

---

## 10. References

- Clearwing mechanism_memory.py: https://github.com/Lazarus-AI/clearwing/blob/main/clearwing/sourcehunt/mechanism_memory.py
- Architecture principles: [architecture.md](architecture.md) §1.2 (Policy type subagents) and §1.4 (Cold Eyes anti-argument design)
- Policy checklist: [policy-checklist-template.md](policy-checklist-template.md)
- Refusal log schema: [refusal-spec.md](refusal-spec.md) §3.2
