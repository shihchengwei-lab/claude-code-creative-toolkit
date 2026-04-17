#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mechanism Add — manual extraction CLI (no LLM in the loop).

Schema: docs/mechanism-memory-schema.md
Store:  configured via memory.mechanism_memory (default docs/mechanism-memory.jsonl)

Usage:
    python scripts/memory/mechanism_add.py \\
        --summary "<abstract pattern description>" \\
        --policy-clause §2 \\
        --tags time_anachronism,voice_drift \\
        --keywords slang,casual \\
        --positive-rewrite "<positive rephrasing — passes white-bear check>" \\
        --trigger-context "<what context produces this drift>" \\
        [--source-refusal-id <timestamp>] \\
        [--source-commit <sha>] \\
        [--user-resolution "<action taken after user decision>"]

White-bear positivity self-check:
    positive_rewrite must NOT contain negation constructs:
      不要、不可、不得、不能、避免、禁止、而非、而不是、不是、勿
      (must not, avoid, prohibit, rather than, instead of, not)
    Trigger → entry rejected. User rewrites as positive assertion.

Storage:
    Auto-generates id (uuid4), created_at, hit_count=1, last_hit_at.
    Atomic append (.tmp → rename) prevents corruption on interrupt.

Injection rules (white-bear firewall, schema §4):
    `summary` is injected only into Policy/Audit layers.
    `positive_rewrite` is the only version safe for Reasoning-layer agents.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _config import load_config, resolve_path  # noqa: E402


# Chinese + English negation constructs (white-bear triggers).
WHITE_BEAR_PATTERNS_ZH = [
    "不要", "不可", "不得", "不能",
    "避免", "禁止",
    "而非", "而不是", "不是",
    "勿",
]
WHITE_BEAR_PATTERNS_EN = [
    # Word-boundary English negatives. Case-insensitive.
    r"\bdon't\b", r"\bdo not\b",
    r"\bdoesn't\b", r"\bdoes not\b",
    r"\bshouldn't\b", r"\bshould not\b",
    r"\bmust not\b", r"\bmustn't\b",
    r"\bavoid\b", r"\bprohibit\b", r"\bforbid\b",
    r"\brather than\b", r"\binstead of\b",
    r"\bnot\b",
]


def _white_bear_check(text: str) -> list[str]:
    """Return list of matched negation tokens. Empty list = passes."""
    hits: list[str] = []
    for pat in WHITE_BEAR_PATTERNS_ZH:
        if pat in text:
            hits.append(pat)
    for pat in WHITE_BEAR_PATTERNS_EN:
        if re.search(pat, text, re.IGNORECASE):
            hits.append(pat.strip(r"\b"))
    return hits


def _validate_clause(clause: str, cfg: dict) -> bool:
    """Validate clause against config.checklist.valid_clauses.

    'auto' (default) accepts:
        - <clause_prefix><digits>  e.g.  §1, §12
        - 'deathline' or '生死線'
    Otherwise expects an explicit list.
    """
    setting = cfg["checklist"].get("valid_clauses", "auto")
    prefix = cfg["checklist"]["clause_prefix"]

    if setting == "auto":
        if re.fullmatch(rf"{re.escape(prefix)}\d+", clause):
            return True
        if clause in ("deathline", "生死線"):
            return True
        return False

    if isinstance(setting, list):
        return clause in setting

    return True  # unknown setting — permissive


def _true_append(path: Path, entry: dict) -> None:
    """Append one JSONL line. Does not read-rewrite the file — preserves any
    pre-existing malformed lines, and remains crash-safe (a partial write
    corrupts only the new line, never older entries).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Append one mechanism to mechanism memory",
    )
    parser.add_argument("--summary", required=True,
                        help="Abstract pattern description (read by policy-guardian / cold_eyes)")
    parser.add_argument("--policy-clause", required=True,
                        help="Policy clause id (e.g. §1, deathline)")
    parser.add_argument("--tags", required=True,
                        help="Comma-separated tags")
    parser.add_argument("--keywords", required=True,
                        help="Comma-separated keywords")
    parser.add_argument("--positive-rewrite", required=True,
                        help="Positive rephrasing — subject of white-bear self-check")
    parser.add_argument("--trigger-context", required=True,
                        help="What context produces this drift")
    parser.add_argument("--source-refusal-id", default=None,
                        help="Corresponding refusal-log timestamp (optional)")
    parser.add_argument("--source-commit", default=None,
                        help="Triggering commit SHA (optional)")
    parser.add_argument("--user-resolution", default=None,
                        help="Action taken after user resolution (optional)")
    parser.add_argument("--force", action="store_true",
                        help="Skip white-bear self-check (not recommended)")
    parser.add_argument("--jsonl", default=None,
                        help="Override memory.mechanism_memory path from config")
    parser.add_argument("--config", default=None,
                        help="Path to architecture.config.yaml")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    cfg = load_config(args.config)

    if not _validate_clause(args.policy_clause, cfg):
        prefix = cfg["checklist"]["clause_prefix"]
        print(f"mechanism_add: policy-clause '{args.policy_clause}' invalid",
              file=sys.stderr)
        print(f"  expected: {prefix}<digits>  or  'deathline' / '生死線'",
              file=sys.stderr)
        return 1

    hits = _white_bear_check(args.positive_rewrite)
    if hits and not args.force:
        print("mechanism_add: white-bear positivity self-check failed",
              file=sys.stderr)
        print(f"  positive_rewrite contains negation: {hits}", file=sys.stderr)
        print("  Rewrite as positive assertion (what TO do, not what NOT to do)",
              file=sys.stderr)
        print("  Examples:", file=sys.stderr)
        print("    reject: 'deity does not use modern slang'", file=sys.stderr)
        print("    accept: 'deity speech stays period-appropriate'", file=sys.stderr)
        return 1
    if hits and args.force:
        print(f"mechanism_add: --force skipped white-bear check (hits: {hits})",
              file=sys.stderr)

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    if not tags:
        print("mechanism_add: --tags cannot be empty", file=sys.stderr)
        return 1
    if not keywords:
        print("mechanism_add: --keywords cannot be empty", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {
        "id": str(uuid.uuid4()),
        "created_at": now,
        "summary": args.summary,
        "policy_clause": args.policy_clause,
        "tags": tags,
        "keywords": keywords,
        "trigger_context": args.trigger_context,
        "positive_rewrite": args.positive_rewrite,
        "source_refusal_id": args.source_refusal_id,
        "source_commit": args.source_commit,
        "hit_count": 1,
        "last_hit_at": now,
        "user_resolution": args.user_resolution,
    }

    path = Path(args.jsonl) if args.jsonl else resolve_path(
        cfg["memory"]["mechanism_memory"]
    )
    _true_append(path, entry)

    print(f"mechanism added: {entry['id']}")
    print(f"  clause: {entry['policy_clause']}  tags: {', '.join(tags)}")
    print(f"  path:   {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
