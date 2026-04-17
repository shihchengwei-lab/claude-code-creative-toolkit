# Policy Checklist — Template

> **Architecture position:** [architecture.md](architecture.md) §3.2
> **Config paths:** `policy_checklist` (file location) + `checklist.*` (parsing regex)

This file is the format contract for the policy checklist consumed by
`scripts/audit/cold_eyes.py`. Copy this template to your `policy_checklist`
location (default `docs/policy-checklist.md`) and fill in your own anchors
and rules.

---

## Header conventions

Cold Eyes parses the checklist with these regex (overridable in config):

| What | Default regex | Captures |
|---|---|---|
| Anchor header | `^## (?:錨點\|Anchor) (\d+)[:：]?` | Anchor number → clause id `<prefix><n>` |
| Deathline header | `^## (?:附錄 A\|Deathline)[:：]?` | Maps to clause id `deathline` |
| Level 2 sub-header | `^### Level 2` | Marks the start of machine-readable rules |
| Clause prefix | `§` | Prepended to anchor numbers (e.g. `§1`, `§2`) |

Both English (`Anchor 1:`) and Chinese (`錨點 1：`) headers are accepted by
default. Add more patterns in `checklist.anchor_header_regex` if you need them.

---

## Two-level granularity

**Level 1** — conceptual anti-patterns. Read by `policy-guardian` only.
Guardian carries context, reads this in plain language.

**Level 2** — machine-readable keyword / regex rules. Read by `cold_eyes`.
Zero-context; must be explicit.

Cold Eyes ignores Level 1 entirely. Guardian may read both levels.

---

## Level 2 syntax (machine-readable)

Two bullet formats inside `### Level 2` blocks are parsed:

### Literal term lists (`Noun` / `Verb` bullets)

Simple word lists — Cold Eyes matches them as escaped substrings:

```markdown
- **Noun**: buff, bonus, efficiency, modifier, booster
- **Verb**: provides, grants, boosts, enhances, increases
```

Chinese equivalents (`名詞` / `動詞`) are also recognized and split on `、` or `,`:

```markdown
- **名詞**: 加成、輔助、強化、效率、配裝
- **動詞**: 提供、賦予、增強、加乘
```

### Regex patterns (`Pattern` / `Negative pattern` bullets)

For numeric, structural, or compound patterns:

```markdown
- **Pattern**
  - `/\+\d+%/`
  - `/\d+x/`
  - `/Lv\.?\d+/`
```

The sub-bullet must be an indented `` - `/regex/` `` line. Whatever is between
the forward slashes is compiled as a Python `re` pattern.

Chinese alias (`數值 pattern` / `風采 negative pattern`) is also recognized.

---

## Full example — Anchor 1

```markdown
## Anchor 1: Players earn through action, not payment

### Level 1 conceptual anti-patterns (guardian)

- Content implies users can unlock progress by paying
- Storefront messaging promises "faster" / "skip wait" pathways
- Currency conversion framed as an equivalent to effort

### Level 2 keyword scan (cold-eyes)

- **Noun**: paywall, premium, booster, skip, fast-track
- **Verb**: unlock, skip, accelerate, fast-forward
- **Pattern**
  - `/pay\s*to\s*(unlock|skip|win)/i`
  - `/premium\s*pass/i`
```

---

## Deathline example

Deathlines are absolute rules (not gradient). They get clause id `deathline`
regardless of the `checklist.clause_prefix`.

```markdown
## Appendix A: Deathlines

### Level 1 conceptual anti-patterns (guardian)

- Claims about medical efficacy for non-medical products
- Discriminatory generalizations by protected characteristic

### Level 2 keyword scan (cold-eyes)

- **Noun**: cure, prescription, diagnosis, treatment
- **Pattern**
  - `/guaranteed\s*(results|cure)/i`
```

---

## Writing style — positive vs negative

The **corpus** (`policy_corpus`) is positive prose:

> *Progress is a record of play — each session is its only source.*

The **checklist** (this file) is allowed to be negative because it's read by
the Policy and Audit layers only — both of which are white-bear-insulated.

**Never** copy checklist text into the corpus. Never copy corpus text into
the checklist. Their layers are different by design.

---

## How to build your own

### One-time bootstrap (reverse extraction)

1. Read your policy corpus and existing review docs
2. For each "must not / is not / forbidden" clause, extract:
   - Concept (Level 1): what the intent is
   - Keyword / regex (Level 2): the machine-readable signature
3. Group by anchor (the top-level principle being protected)

### Ongoing (event accumulation)

Every user report of "this shouldn't have happened" →

1. Identify which anchor was breached
2. Add a Level 1 entry describing the conceptual pattern
3. If the breach has a machine-detectable signature, add a Level 2 entry

### What **not** to do

Don't benchmark against comparable products and import their rules wholesale.
That adds rules your system never intended to uphold, diluting the anchor.
Grow the checklist from your own corpus and your own incidents only.

---

## Testing the checklist

After editing, sanity-check that Cold Eyes parses it:

```bash
# Point cold_eyes at your checklist without any diff
python scripts/audit/cold_eyes.py --scope working --checklist docs/policy-checklist.md
# Expected: JSON output (pass:true if no violating diff lines, or issues list)
```

If Cold Eyes reports `checklist produced no rules`, your Level 2 blocks don't
match the expected bullet format — recheck the header patterns and bullet syntax.
