# Classify Rules — Template

> **Architecture position:** [architecture.md](architecture.md) §1.3
> **Implementation:** `scripts/audit/classify.py`
> **Config path:** `classify.*` in `architecture.config.yaml`

## 0. Principle

Classify is a pure decomposer (decomposer). **It never approves output.**

- Input: composite output (forward) or composite fail list (backward)
- Output: atomic units + dispatch target list
- Implemented as a pure script (no LLM) to resist drift and rhetoric
- Whitelist changes require a config commit (never runtime expansion)

Two trigger points share one script:

- **Forward split** (after Main Agent output): path → subagent dispatch
- **Backward split** (after Cold Eyes fail): issue type / clause → fix target

---

## 1. Forward split routing

Defined under `classify.path_rules` in config, as a list of glob-to-dispatch rules.

### Example rules (generic project)

```yaml
classify:
  path_rules:
    # Source code
    - pattern: 'src/**/*.ts'
      dispatch: [dev-agent, qa-agent]
    - pattern: 'src/**/*.py'
      dispatch: [dev-agent, qa-agent]
    - pattern: 'test/**/*'
      dispatch: [qa-agent]

    # Infrastructure
    - pattern: 'db/migrations/*.sql'
      dispatch: [dev-agent, migration-reviewer, qa-agent]
    - pattern: 'terraform/**/*.tf'
      dispatch: [infra-agent, code-reviewer]

    # User-visible content
    - pattern: 'content/**/*.md'
      dispatch: [policy-guardian]
    - pattern: 'copy/**/*.md'
      dispatch: [policy-guardian]

  # Paths always routed to the Policy layer (e.g. anything containing
  # player-facing text embedded in source code)
  policy_paths_glob:
    - 'src/**/*copy*.ts'
    - 'src/**/*text*.ts'

  # Paths skipped entirely
  whitelist_exact:
    - CLAUDE.md
    - docs/session-state.md
    - docs/refusal-log.jsonl

  whitelist_glob:
    - 'docs/plans/*.md'
    - '.git/**'
    - '.claude/**'
    - 'build/**'
```

### Composite content principle

- A single file matching multiple patterns → **dispatch to the union** (over-audit is safer than under-audit)
- No match → fallback to `unclassified` (Main Agent resolves manually)
- `--hint <category>` can manually attach (commit message should explain why)

---

## 2. Backward split routing

When Cold Eyes fails with `{pass: false, issues: [{policy_clause, type}, ...]}`,
the backward split routes each issue to its fix target via
`classify.issue_type_rules`.

### Example issue-type rules

```yaml
classify:
  issue_type_rules:
    # Policy-layer issues
    anchor-violation:      [main-agent]
    deathline-violation:   [main-agent]
    tone-drift:            [policy-guardian]
    white-bear-lex:        [policy-guardian]

    # Code-layer issues
    logic-error:           [dev-agent]
    test-failure:          [dev-agent, qa-agent]
    security:              [dev-agent]
    dangling-reference:    [dev-agent]

    # Infra-layer issues
    migration-risk:        [migration-reviewer, dev-agent]

    # Asset-layer issues
    asset-naming-drift:    [asset-agent]
    asset-tech-audit-fail: [asset-agent]
```

### Merge rules

- One task's issues list may mix multiple types → dispatch all in parallel
- One target dispatched for multiple issues → the caller merges them into a single prompt
- No type and no clause prefix match → fallback to `main-agent` (escalate one layer up)

---

## 3. Script usage

```bash
# Forward split — multiple files
python scripts/audit/classify.py forward --files \
  src/feature.ts \
  content/landing.md \
  docs/session-state.md

# Expected (JSON):
# {
#   "src/feature.ts":          ["dev-agent", "qa-agent"],
#   "content/landing.md":      ["policy-guardian"],
#   "docs/session-state.md":   ["whitelist"]
# }

# Backward split — from Cold Eyes output
python scripts/audit/classify.py backward --issues \
  '[{"policy_clause":"§4","type":"anchor-violation"},
    {"policy_clause":"§2","type":"tone-drift"}]'

# Expected:
# [
#   {"issue": {...}, "dispatch": ["main-agent"]},
#   {"issue": {...}, "dispatch": ["policy-guardian"]}
# ]

# Manual hint attachment
python scripts/audit/classify.py forward --files foo.ts --hint guardian
```

---

## 4. Prohibitions

- Using an LLM for semantic routing (must be pure regex / lookup)
- Runtime-expanding the whitelist (config commits only)
- Letting classify approve output (always dispatch, never verdict)
- Bypassing classify for direct commit (Cold Eyes only audits what passed guardian)
- Main Agent self-dispatching (dispatch always goes through classify)

---

## 5. Event accumulation

When the same type of mis-dispatch / missed-dispatch recurs ≥ 3 times, that is
a signal to revise the architecture: update `classify.path_rules` or
`issue_type_rules` in config (and, if needed, the policy checklist appendix
that logs such events).
