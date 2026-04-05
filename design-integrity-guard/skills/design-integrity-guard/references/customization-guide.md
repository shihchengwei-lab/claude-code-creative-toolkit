# Customization Guide

How to adapt the Design Integrity Guard for your project.

如何將 Design Integrity Guard 套用到你的專案。

---

## Step 1: Write your design-principles.md

Copy `docs/design-principles-template.md` → rename to `docs/design-principles.md` → fill in each section.

Tips:
- **「這個產品是什麼」** — Write one sentence about the soul, not features. Bad: "A task management app with AI." Good: "A place where your scattered thoughts become calm, clear plans."
- **「絕對不能變成什麼」** — Think of products you hate. What would make someone say "ugh, this is just another ___"? That's your death line.
- **「禁用詞彙」** — Browse competitor apps. The words that make you cringe go here.
- **「最終判準」** — If your agent can only remember one rule, this is it. Make it vivid and sensory.

See `docs/design-principles-example.md` for a filled-in example.

---

## Step 2: Customize SKILL.md checklists

The checklists in `SKILL.md` are templates with blanks (`自訂：___`). Fill them in for your product:

```markdown
### 對話/互動文字
- [ ] 關係深化的方向是「越安靜越有重量」     ← fill this
- [ ] 禁止的方向是「越來越撒嬌」             ← fill this
- 自訂：不用表情符號                         ← add your own
```

You can also:
- **Delete** content types you don't have (e.g., remove "商店/付費文字" if you have no store)
- **Add** new content types specific to your product (e.g., "push notification copy", "onboarding flow")

---

## Step 3: Add CLAUDE.md anchors

Add 3-5 lines to your project's `CLAUDE.md`. These are the non-negotiable lines that survive context compaction:

```markdown
## Design Integrity
- All user-facing text MUST pass design-integrity-guard skill review.
- Read docs/design-principles.md before writing or reviewing any user-visible content.
- When uncertain whether content violates principles, reject and ask for revision.
```

Keep it short. Every unnecessary line in CLAUDE.md dilutes the ones that matter.

---

## Step 4 (optional): Deploy the guardian agent

If you use multi-agent architecture with a PM agent:

1. Copy `agents/content-guardian.md` to your project's `agents/` folder
2. Add auto-trigger rules to your PM agent:
   - Route any deliverable containing user-visible text to content-guardian for review
   - Route any notification/error/alert text to content-guardian for review
3. The guardian reviews against your design-principles.md and returns violations with specific citations

If you're a solo developer without a PM agent, you can still use the skill directly — just load it manually when writing user-facing content:

```
Load skill design-integrity-guard and review the following UI text against our design principles: [paste text]
```

---

## Common customization patterns

**For games:** Add content types for dialogue, character descriptions, item descriptions, quest text. Emphasize "world voice" over "system voice" in your final criterion.

**For SaaS/B2B:** Add content types for onboarding copy, empty states, error messages, email templates. Focus禁用詞彙 on jargon and corporate-speak.

**For content/media apps:** Add content types for headlines, summaries, recommendations. Focus on tone consistency across automated and human-written content.

**For multi-language products:** Pair with a translator-localizer agent (see `non-engineering-agents/`). Each language needs its own prohibited vocabulary list, but the design principles stay universal.
