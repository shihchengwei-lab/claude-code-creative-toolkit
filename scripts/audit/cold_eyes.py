#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cold Eyes — zero-context policy auditor (Audit layer).

Scans `git diff` against policy-checklist regex rules and emits a minimal
binary pass/fail verdict. Never sees task requirements, prior conversation,
or subagent reports — only the diff and the checklist.

Output schema:
    {"pass": true|false, "issues": [{"policy_clause": "§1", "type": "anchor-violation"}]}

Exit codes:
    0 = pass
    1 = fail (issues found)
    2 = infrastructure failure (git error, checklist parse error)

Usage:
    python scripts/audit/cold_eyes.py                   # scope=working tree diff
    python scripts/audit/cold_eyes.py --scope staged    # staged diff (pre-commit)
    python scripts/audit/cold_eyes.py --diff path.diff  # from file
    echo "<diff>" | python scripts/audit/cold_eyes.py --diff -

Types (type enum):
    anchor-violation    — clause Level-2 regex hit
    deathline-violation — deathline Level-2 regex hit

Design:
    - Classify backward split reads (policy_clause, type) for routing
    - Zero-argument space: no severity/confidence/evidence/fix fields
    - The checklist is the single source of truth; this script only parses it

Spec: docs/architecture.md
Theory: https://github.com/shihchengwei-lab/separation-and-audit-alignment
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _config import load_config, resolve_path  # noqa: E402


# Checklist bullet patterns — format-level, accepted as convention.
NOUN_VERB_BULLET_RE = re.compile(
    r"^- \*\*(名詞|動詞|Noun|Verb)\*\*[:：]\s*(.+)$"
)
PATTERN_HEADER_RE = re.compile(
    r"^- \*\*(數值 pattern|風采 negative pattern|Pattern|Negative pattern)\*\*"
)
PATTERN_SUB_RE = re.compile(r"^\s+- `/(.+)/`")


def parse_checklist(path: Path, cfg: dict) -> list[dict]:
    """Parse policy-checklist.md Level-2 blocks into rules.

    Each rule: {"clause": str, "type": str, "pattern": re.Pattern, "source": str}
    """
    text = path.read_text(encoding="utf-8")
    anchor_re = re.compile(cfg["checklist"]["anchor_header_regex"])
    deathline_re = re.compile(cfg["checklist"]["deathline_header_regex"])
    level2_re = re.compile(cfg["checklist"]["level2_header_regex"])
    clause_prefix = cfg["checklist"]["clause_prefix"]
    other_h2_re = re.compile(r"^## ")
    other_h3_re = re.compile(r"^### ")

    rules: list[dict] = []
    current_clause = None
    current_type = None
    in_level2 = False
    in_pattern_block = False

    for line in text.splitlines():
        m = anchor_re.match(line)
        if m:
            current_clause = f"{clause_prefix}{m.group(1)}"
            current_type = "anchor-violation"
            in_level2 = False
            in_pattern_block = False
            continue
        if deathline_re.match(line):
            current_clause = "deathline"
            current_type = "deathline-violation"
            in_level2 = False
            in_pattern_block = False
            continue
        if other_h2_re.match(line):
            current_clause = None
            current_type = None
            in_level2 = False
            in_pattern_block = False
            continue

        if current_clause is None:
            continue

        if level2_re.match(line):
            in_level2 = True
            in_pattern_block = False
            continue
        if other_h3_re.match(line):
            in_level2 = False
            in_pattern_block = False
            continue

        if not in_level2:
            continue

        m = NOUN_VERB_BULLET_RE.match(line)
        if m:
            in_pattern_block = False
            terms = [t.strip() for t in re.split(r"[、,]", m.group(2)) if t.strip()]
            for t in terms:
                try:
                    rules.append({
                        "clause": current_clause,
                        "type": current_type,
                        "pattern": re.compile(re.escape(t)),
                        "source": t,
                    })
                except re.error:
                    pass
            continue

        if PATTERN_HEADER_RE.match(line):
            in_pattern_block = True
            continue

        if in_pattern_block:
            m = PATTERN_SUB_RE.match(line)
            if m:
                pat_src = m.group(1)
                try:
                    rules.append({
                        "clause": current_clause,
                        "type": current_type,
                        "pattern": re.compile(pat_src),
                        "source": f"/{pat_src}/",
                    })
                except re.error:
                    pass
                continue
            if line.strip() == "":
                continue
            in_pattern_block = False

    return rules


def _git_root() -> Path:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", check=True,
        )
        return Path(r.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def get_git_diff(scope: str = "working") -> str:
    args = ["git", "diff"]
    if scope == "staged":
        args.append("--cached")
    elif scope == "head":
        args = ["git", "diff", "HEAD"]
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(f"cold_eyes: git diff failed — {r.stderr}", file=sys.stderr)
        sys.exit(2)
    return r.stdout


DIFF_FILE_HEADER_RE = re.compile(r"^diff --git a/(\S+) b/\S+")


def is_excluded(filepath: str, excluded_files: set[str],
                excluded_dirs: tuple[str, ...]) -> bool:
    if filepath in excluded_files:
        return True
    return any(filepath.startswith(d) for d in excluded_dirs)


def scan_diff(diff_text: str, rules: list[dict], cfg: dict) -> list[dict]:
    """Scan `+` added lines in diff. Returns deduped issues [{policy_clause, type}]."""
    excluded_files = set(cfg["audit"]["excluded_files"])
    excluded_dirs = tuple(cfg["audit"]["excluded_dirs"])

    current_file = None
    skip_current = False
    added_lines: list[str] = []

    for line in diff_text.splitlines():
        m = DIFF_FILE_HEADER_RE.match(line)
        if m:
            current_file = m.group(1).replace("\\", "/")
            skip_current = is_excluded(current_file, excluded_files, excluded_dirs)
            continue
        if skip_current:
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added_lines.append(line[1:])

    if not added_lines:
        return []

    joined = "\n".join(added_lines)
    seen: set[tuple[str, str]] = set()
    issues: list[dict] = []
    for rule in rules:
        if rule["pattern"].search(joined):
            key = (rule["clause"], rule["type"])
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                "policy_clause": rule["clause"],
                "type": rule["type"],
            })
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cold Eyes — zero-context policy auditor",
    )
    parser.add_argument("--scope", default="working",
                        choices=["working", "staged", "head"],
                        help="git diff scope (default: working)")
    parser.add_argument("--diff", default=None,
                        help="Read diff from file ('-' for stdin). Overrides --scope.")
    parser.add_argument("--checklist", default=None,
                        help="Override policy_checklist path from config")
    parser.add_argument("--config", default=None,
                        help="Path to architecture.config.yaml")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    cfg = load_config(args.config)
    repo = _git_root()

    if args.checklist:
        checklist_path = Path(args.checklist)
    else:
        checklist_path = resolve_path(cfg["policy_checklist"], repo)

    if not checklist_path.exists():
        print(f"cold_eyes: checklist not found — {checklist_path}", file=sys.stderr)
        return 2

    try:
        rules = parse_checklist(checklist_path, cfg)
    except Exception as exc:
        print(f"cold_eyes: checklist parse failed — {exc}", file=sys.stderr)
        return 2

    if not rules:
        print("cold_eyes: checklist produced no rules", file=sys.stderr)
        return 2

    if args.diff:
        if args.diff == "-":
            diff_text = sys.stdin.read()
        else:
            diff_text = Path(args.diff).read_text(encoding="utf-8")
    else:
        diff_text = get_git_diff(args.scope)

    issues = scan_diff(diff_text, rules, cfg)
    result = {"pass": len(issues) == 0, "issues": issues}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
