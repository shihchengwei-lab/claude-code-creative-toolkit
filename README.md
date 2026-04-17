# Separation & Audit — Claude Code Reference Implementation

**A runnable reference implementation of the [separation-and-audit-alignment](https://github.com/shihchengwei-lab/separation-and-audit-alignment) architecture for Claude Code multi-agent projects.**

> Alignment becomes less a conversational property of a single model,
> and more an architectural property of the overall system.
>
> — from the theory repo

Instead of asking one model to reason, self-monitor, and hold refusal authority
at once, this repo splits those roles into **independent pipeline layers** with
no cross-layer argument surface. The result: long sessions don't erode the
boundary, and refusals become cold data rather than negotiable events.

This is v2.0 of what was previously `claude-code-creative-toolkit`. The v1 toolkit
is preserved under [`examples/creative-writing/`](examples/creative-writing/).

---

## What this gives you

Six components, each as a concrete file or script:

| Layer | Component | Where |
|---|---|---|
| Reasoning | Main Agent | your PM / primary Claude Code session |
| Policy (text) | `policy-guardian` | [`agents/policy-guardian.md`](agents/policy-guardian.md) |
| Policy (code) | `code-reviewer` | [`agents/code-reviewer.md`](agents/code-reviewer.md) |
| Policy (infra) | `migration-reviewer` | [`agents/migration-reviewer.md`](agents/migration-reviewer.md) |
| Classify (decomposer) | `scripts/audit/classify.py` | config-driven routing |
| Audit (Cold Eyes) | `scripts/audit/cold_eyes.py` + `cold_eyes_gate.py` | pre-commit layer |
| Memory (cross-session) | `scripts/memory/mechanism_*.py` | mechanism memory + refusal log |
| Gates | `scripts/gates/secret_scan.py` + pre-commit template | configurable layers |
| Observability | `scripts/observability/health_digest.py` + session-start hook | threshold-triggered reminders |

Everything is driven by one file: [`config/architecture.config.example.yaml`](config/architecture.config.example.yaml).

---

## Quick start

```bash
# 1. Clone or vendor this repo into your project root (or adjacent to it).
git clone https://github.com/shihchengwei-lab/separation-and-audit-claude-code

# 2. Install the single runtime dependency (PyYAML for config parsing).
pip install -r requirements.txt

# 3. Copy the example config into your project root.
cp config/architecture.config.example.yaml architecture.config.yaml

# 4. Point it at your own policy corpus and policy checklist.
#    (You write those — see docs/policy-checklist-template.md for the format.)

# 5. Install the pre-commit hook template.
cp scripts/git-hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# 6. Register the session-start hook in your Claude Code settings.
#    See docs/refusal-spec.md §6.1 for the JSON snippet.
```

Then copy the `agents/*.md` files into your project's `.claude/agents/`
directory and dispatch them via the normal Claude Code subagent flow.

---

## How the pipeline works

```
User request
     ↓
Main Agent (Reasoning)  — reads positive policy corpus only
     ↓
Classify [forward split]  — pure script, config-driven routing
     ↓
Subagents (policy-guardian / code-reviewer / qa-agent / ...) — local review
     ↓
【Cold Eyes #1】  — zero-context audit against policy checklist Level 2
     ├─ pass → commit
     └─ fail → Classify [backward split] → fix → 【Cold Eyes #2】
                                                   ├─ pass → commit
                                                   └─ fail → Unified Refusal
                                                              (log; stop; wait for user)
```

Full architectural reasoning: [`docs/architecture.md`](docs/architecture.md).

---

## Key design ideas

**White-bear isolation.** Negation phrasing is kept out of the Reasoning layer.
Main Agent reads only positive policy; the Policy layer reads the negation
version; Reasoning never activates "don't think of a white bear" patterns.

**Zero-context Cold Eyes.** The final audit sees only diff + policy — no
conversation, no requirements, no subagent reports. This removes every surface
on which rhetoric could persuade it to soften.

**Bounded retry + silent refusal.** Cold Eyes runs at most twice. The second
fail writes a structured refusal log and **does not return to the generation
layer** — Main Agent literally does not know it happened. The user discovers
pending refusals via a session-start hook or the status CLI, and resolves them
offline.

**Mechanism memory, two-field design.** Cross-session drift-pattern memory with
a hard white-bear firewall: the negation-phrased `summary` is injected only
into Policy / Audit agents; the positive `positive_rewrite` is the only
version safe for Reasoning.

**Config over convention.** Almost every path, regex, layer, and rule is in
one `architecture.config.yaml`. Reinstall the template in a new project, point
at your corpus, and the whole pipeline runs.

---

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — full six-component spec
- [`docs/refusal-spec.md`](docs/refusal-spec.md) — Unified Refusal module
- [`docs/mechanism-memory-schema.md`](docs/mechanism-memory-schema.md) — memory layer
- [`docs/policy-checklist-template.md`](docs/policy-checklist-template.md) — checklist format
- [`docs/classify-rules-template.md`](docs/classify-rules-template.md) — Classify routing

## Examples

- [`examples/creative-writing/`](examples/creative-writing/) — the former v1.x
  toolkit, kept as a domain-specific use case. Shows how the generic
  architecture maps onto content / storytelling work.

---

## Relationship to the theory repo

This repo is the **reference implementation** of the architecture proposed in
[shihchengwei-lab/separation-and-audit-alignment](https://github.com/shihchengwei-lab/separation-and-audit-alignment).

- The theory repo (CC BY 4.0) documents the alignment distortion patterns
  observed in long LLM sessions and argues for pipeline-level authority separation
- This repo (MIT) implements that pipeline concretely for Claude Code

If you cite the theory, cite the theory repo. If you fork the implementation,
this repo's MIT license applies.

---

## What this is not

- **Not a canned prompt pack.** You write your own policy corpus and checklist;
  the repo supplies the pipeline that enforces them.
- **Not a replacement for testing.** Cold Eyes audits policy conformance on
  diff; it does not replace your test suite. Pair it with your project's CI.
- **Not a short-conversation product solution.** Unified Refusal is
  session-terminal by design — appropriate for autonomous agents, not for
  chatbots where the user needs to negotiate.

---

## Status

v2.0 (2026-04-18) — first release under the new name.
See the migration notes in [`examples/creative-writing/README.md`](examples/creative-writing/README.md)
if you were using v1.x as `claude-code-creative-toolkit`.

## License

MIT. See [LICENSE](LICENSE).
