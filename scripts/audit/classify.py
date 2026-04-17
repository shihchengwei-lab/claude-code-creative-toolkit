#!/usr/bin/env python3
"""Classify — pure decomposer (Classify layer).

Never approves output — only routes.

Forward split:  paths → subagent names (based on config.classify.path_rules).
Backward split: issues → fix-target agent names (based on config.classify.issue_type_rules).

Spec: docs/classify-rules-template.md
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _config import load_config  # noqa: E402


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


def _glob_match(path: str, pattern: str) -> bool:
    path = _normalize(path)
    pattern = _normalize(pattern)
    if "**" not in pattern:
        return fnmatch.fnmatch(path, pattern)

    # Standard glob semantics: /**/ matches zero or more path segments.
    # e.g. `src/**/*.ts` must match `src/foo.ts` (zero) AND `src/a/b/foo.ts` (two).
    # Build the regex via escape → substitute, handling /**/, **/, /**, ** in order.
    regex = re.escape(pattern)
    regex = regex.replace(r"/\*\*/", "(?:/.*)?/")  # /**/ : zero-or-more segments with slash
    regex = regex.replace(r"\*\*/", "(?:.*/)?")    # **/  at start : zero-or-more leading segments
    regex = regex.replace(r"/\*\*", "(?:/.*)?")    # /**  at end   : zero-or-more trailing segments
    regex = regex.replace(r"\*\*", ".*")           # standalone ** : any char including slash
    regex = regex.replace(r"\*", "[^/]*")          # single * : within-segment wildcard
    regex = regex.replace(r"\?", ".")
    return re.fullmatch(regex, path) is not None


def _any_match(path: str, patterns: Iterable[str]) -> bool:
    return any(_glob_match(path, p) for p in patterns)


def _add(targets: list[str], value: str) -> None:
    if value not in targets:
        targets.append(value)


def classify_forward_single(path: str, cfg: dict,
                            hints: list[str] | None = None) -> list[str]:
    hints = hints or []
    path = _normalize(path)
    c = cfg["classify"]

    # Whitelist short-circuit
    if path in set(c.get("whitelist_exact", [])) \
            or _any_match(path, c.get("whitelist_glob", [])):
        return ["whitelist"]

    targets: list[str] = []

    # Policy-path routing (user-visible content)
    if path in set(c.get("policy_paths_exact", [])) \
            or _any_match(path, c.get("policy_paths_glob", [])):
        _add(targets, "policy-guardian")

    # Custom path rules: list of {pattern, dispatch: [...]}
    for rule in c.get("path_rules", []) or []:
        pattern = rule.get("pattern")
        if not pattern:
            continue
        if _glob_match(path, pattern):
            for t in rule.get("dispatch", []):
                _add(targets, t)

    # Explicit hints override
    hint_map = {
        "guardian": "policy-guardian",
        "policy": "policy-guardian",
        "dev": "dev-agent",
        "qa": "qa-agent",
        "art": "art-agent",
    }
    for hint in hints:
        target = hint_map.get(hint)
        if target:
            _add(targets, target)

    if not targets:
        targets = ["unclassified"]
    return targets


def classify_forward(files: list[str], cfg: dict,
                     hints: list[str] | None = None) -> dict[str, list[str]]:
    return {f: classify_forward_single(f, cfg, hints) for f in files}


def classify_backward_single(issue: dict, cfg: dict) -> list[str]:
    itype = issue.get("type", "")
    rules = cfg["classify"].get("issue_type_rules", {}) or {}

    targets: list[str] = []
    for t in rules.get(itype, []):
        _add(targets, t)

    if not targets:
        targets = ["main-agent"]
    return targets


def classify_backward(issues: list[dict], cfg: dict) -> list[dict]:
    return [{"issue": i, "dispatch": classify_backward_single(i, cfg)} for i in issues]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        prog="classify",
        description="Pure decomposer — forward/backward split. Never approves output.",
    )
    parser.add_argument("--config", default=None,
                        help="Path to architecture.config.yaml")
    sub = parser.add_subparsers(dest="mode", required=True)

    fwd = sub.add_parser("forward", help="paths → subagents")
    fwd.add_argument("--files", nargs="+", required=True)
    fwd.add_argument("--hint", nargs="*", default=[],
                     choices=["guardian", "policy", "dev", "qa", "art"])

    bwd = sub.add_parser("backward", help="issues → fix targets")
    bwd.add_argument("--issues", required=True,
                     help="JSON array of issues")

    args = parser.parse_args()
    cfg = load_config(args.config)

    if args.mode == "forward":
        result = classify_forward(args.files, cfg, args.hint)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.mode == "backward":
        try:
            issues = json.loads(args.issues)
        except json.JSONDecodeError as e:
            print(f"invalid JSON: {e}", file=sys.stderr)
            return 2
        if not isinstance(issues, list):
            print("issues must be a JSON array", file=sys.stderr)
            return 2
        result = classify_backward(issues, cfg)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
