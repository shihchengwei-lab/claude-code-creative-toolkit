# Example: Creative-writing project

This directory is the **creative-writing use case** of the Separation & Audit
architecture — the original content of `claude-code-creative-toolkit` v1.x,
preserved for reference.

If you're running a game / storytelling / content-producing project with
Claude Code multi-agent, this example shows how the generic architecture
maps onto content work.

> **Note:** the three sub-directories below are v1.x material. They were
> written before the full Separation & Audit architecture existed. They are
> still useful as pattern references, but the production-grade implementation
> lives at the repo root (`scripts/`, `agents/`, `docs/`, `config/`).
>
> When in conflict, prefer the root-level implementation — it's the current
> reference implementation of the theory.

---

## Sub-directories

### `design-integrity-guard/`

Original three-layer defense: CLAUDE.md anchors → design-principles doc →
guard skill + guardian agent.

**In v2 terms:** this is exactly the **Policy layer** of the architecture,
seen from the creative angle. The equivalent production components are:

| v1 (here) | v2 (root) |
|---|---|
| `design-principles.md` anchors | `policy_corpus` + `policy_checklist` |
| `canon-guard` skill | Level 1 rules in `policy_checklist` |
| `design-guardian` agent | `agents/policy-guardian.md` |

The v1 docs here still read well as **concept introduction** to why design
integrity matters. For a production deployment, use the v2 pieces at the root.

### `non-engineering-agents/`

Content Guardian (copy reviewer) and Art Director (asset reviewer) agent templates.

**In v2 terms:** Content Guardian collapses into `policy-guardian`.
Art Director remains a separate Execution-type subagent (it generates,
not reviews) — no direct root equivalent because it's domain-specific;
use it as a pattern when you build your own creative subagents.

### `token-conservation/`

Behavioral constraints on dispatch format, report format, session state summary,
and skill lazy-loading — all aimed at keeping context window usage sane.

**In v2 terms:** still 100% applicable. The architecture assumes efficient
subagent dispatch; the patterns here (four-line dispatch, one-line report)
are exactly the kind of discipline v2 relies on. Think of this as the
**operational discipline layer** sitting on top of the v2 structural layer.

---

## Migration from v1.x

If you were using `claude-code-creative-toolkit` v1:

1. Keep the three sub-directories here as reference — they still work
2. For new projects, start at the repo root and follow [docs/architecture.md](../../docs/architecture.md)
3. Your existing `design-principles.md` is the seed for your v2 `policy_corpus`
4. Your existing `design-guardian.md` becomes a domain-specialized variant of
   `agents/policy-guardian.md`
5. The v2 addition of **Cold Eyes** (zero-context audit), **retry+refusal**,
   and **mechanism memory** are the main things new — they address the
   failure modes v1 could not handle (boundary-justification collapse in
   long sessions, and repeated-violation accumulation across sessions)

The core idea is the same: **don't let the creative agent audit itself.**
v2 just makes that idea structural instead of behavioral.
