#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""refusal_status — list / resolve / stats refusal_log entries.

Spec: docs/refusal-spec.md

CLI:
  # Inspect
  python scripts/memory/refusal_status.py                     # list pending
  python scripts/memory/refusal_status.py --all               # include resolved
  python scripts/memory/refusal_status.py --stats             # aggregate stats

  # Resolve (in-place update + atomic rewrite)
  python scripts/memory/refusal_status.py --resolve N \\
      --decision {fix-policy|abandon|split|architecture} \\
      --notes "..."

  # Resolve + interactive mechanism extraction (calls mechanism_add.py)
  python scripts/memory/refusal_status.py --resolve N \\
      --decision fix-policy --notes "..." \\
      --extract-mechanism

Index N is 1-based in --all order (stable across operations since log is append-only).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _config import load_config, resolve_path  # noqa: E402


VALID_DECISIONS = ("fix-policy", "abandon", "split", "architecture")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _save_atomic(path: Path, entries: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _format_entry(idx: int, e: dict) -> str:
    files = ", ".join(e.get("output_artifact", {}).get("files", []))
    clauses = ", ".join(e.get("policy_clauses", []))
    types = ", ".join(e.get("issue_types", []))
    lines = [
        f"[{idx}] {e.get('timestamp', '?')}",
        f"    task_id:        {e.get('task_id', '?')}",
        f"    files:          {files}",
        f"    policy_clauses: {clauses}",
        f"    issue_types:    {types}",
    ]
    decision = e.get("user_decision")
    if decision:
        lines.append(f"    decision:       {decision} @ {e.get('resolved_at', '?')}")
        notes = e.get("user_decision_notes")
        if notes:
            lines.append(f"    notes:          {notes}")
    return "\n".join(lines)


def _print_stats(entries: list[dict]) -> None:
    if not entries:
        print("no refusals logged")
        return

    decisions = Counter(e.get("user_decision") or "pending" for e in entries)
    clauses: Counter = Counter()
    types: Counter = Counter()
    for e in entries:
        for c in e.get("policy_clauses", []):
            clauses[c] += 1
        for t in e.get("issue_types", []):
            types[t] += 1

    timestamps = sorted(
        e.get("timestamp", "") for e in entries if e.get("timestamp")
    )
    first = timestamps[0] if timestamps else "?"
    last = timestamps[-1] if timestamps else "?"

    print(f"total: {len(entries)}")
    print(f"range: {first} → {last}")
    print()
    print("by user_decision:")
    for d, n in decisions.most_common():
        print(f"  {d:25s} {n:4d}")
    print()
    print("by policy_clause:")
    for c, n in clauses.most_common():
        print(f"  {c:25s} {n:4d}")
    print()
    print("by issue_type:")
    for t, n in types.most_common():
        print(f"  {t:25s} {n:4d}")


def _extract_mechanism_interactive(entry: dict, notes: str,
                                   scripts_root: Path) -> int:
    """Interactive mechanism extraction → calls mechanism_add.py.

    Pre-fills source_refusal_id / source_commit / user_resolution.
    User provides summary / policy-clause / tags / keywords /
    positive-rewrite / trigger-context.
    mechanism_add.py performs white-bear positivity check.
    """
    print("\n--- Mechanism extraction (Ctrl-C to cancel) ---", file=sys.stderr)
    print("Tip: positive-rewrite must read as a positive assertion", file=sys.stderr)
    print("     (negation words trigger the white-bear check)", file=sys.stderr)
    print("", file=sys.stderr)

    try:
        summary = input("summary (abstract pattern): ").strip()
        clause = input("policy-clause (e.g. §1, deathline): ").strip()
        tags = input("tags (comma-separated): ").strip()
        keywords = input("keywords (comma-separated): ").strip()
        positive_rewrite = input("positive-rewrite (positive version): ").strip()
        trigger_context = input("trigger-context (what context): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nExtraction cancelled (decision already written)", file=sys.stderr)
        return 0

    if not all([summary, clause, tags, keywords, positive_rewrite, trigger_context]):
        print("required fields incomplete, extraction cancelled", file=sys.stderr)
        return 1

    diff_hash = entry.get("output_artifact", {}).get("diff_hash", "")
    source_commit = diff_hash[:12] if diff_hash else ""

    cmd = [
        sys.executable, str(scripts_root / "memory" / "mechanism_add.py"),
        "--summary", summary,
        "--policy-clause", clause,
        "--tags", tags,
        "--keywords", keywords,
        "--positive-rewrite", positive_rewrite,
        "--trigger-context", trigger_context,
        "--source-refusal-id", entry.get("timestamp", ""),
        "--user-resolution", notes,
    ]
    if source_commit:
        cmd.extend(["--source-commit", source_commit])

    r = subprocess.run(cmd)
    return r.returncode


def _resolve(args: argparse.Namespace, scripts_root: Path, path: Path,
             entries: list[dict]) -> int:
    if args.decision not in VALID_DECISIONS:
        print(f"--decision must be one of {VALID_DECISIONS}", file=sys.stderr)
        return 1

    if not entries:
        print("refusal log is empty", file=sys.stderr)
        return 1

    if args.resolve < 1 or args.resolve > len(entries):
        print(f"index {args.resolve} out of range (1 ~ {len(entries)})",
              file=sys.stderr)
        print("  use --all to view resolvable entries", file=sys.stderr)
        return 1

    entry = entries[args.resolve - 1]

    if entry.get("user_decision"):
        print(f"entry [{args.resolve}] already resolved: "
              f"{entry['user_decision']} @ {entry.get('resolved_at', '?')}",
              file=sys.stderr)
        return 1

    notes = args.notes or ""
    entry["user_decision"] = args.decision
    entry["user_decision_notes"] = notes if notes else None
    entry["resolved_at"] = _iso_now()

    _save_atomic(path, entries)

    print(f"refusal [{args.resolve}] resolved → {args.decision}")
    print(f"  timestamp:   {entry.get('timestamp', '?')}")
    print(f"  notes:       {notes if notes else '(empty)'}")
    print(f"  resolved_at: {entry['resolved_at']}")

    if args.extract_mechanism:
        extract_exit = _extract_mechanism_interactive(entry, notes, scripts_root)
        if extract_exit != 0:
            return extract_exit

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List / resolve / stats refusals from refusal_log"
    )
    parser.add_argument("--all", action="store_true", help="Include resolved entries")
    parser.add_argument("--stats", action="store_true",
                        help="Aggregate stats (no per-entry detail)")
    parser.add_argument("--resolve", type=int, default=None, metavar="N",
                        help="Resolve entry N (1-based --all order)")
    parser.add_argument("--decision", default=None,
                        choices=VALID_DECISIONS,
                        help="Decision (use with --resolve)")
    parser.add_argument("--notes", default=None,
                        help="Decision rationale (use with --resolve)")
    parser.add_argument("--extract-mechanism", action="store_true",
                        help="After resolve, interactively extract a mechanism")
    parser.add_argument("--config", default=None,
                        help="Path to architecture.config.yaml")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    cfg = load_config(args.config)
    path = resolve_path(cfg["audit"]["refusal_log"])
    scripts_root = Path(__file__).resolve().parent.parent

    entries = _load_entries(path)
    pending = [e for e in entries if e.get("user_decision") is None]
    resolved = [e for e in entries if e.get("user_decision") is not None]

    if args.resolve is not None:
        if args.decision is None:
            print("--resolve requires --decision", file=sys.stderr)
            return 1
        return _resolve(args, scripts_root, path, entries)

    if args.stats:
        _print_stats(entries)
        return 0

    if not args.all:
        if not pending:
            print("no pending refusals")
            return 0
        print(f"pending refusals: {len(pending)}\n")
        for i, e in enumerate(entries, 1):
            if e.get("user_decision") is None:
                print(_format_entry(i, e))
                print()
        print("Resolve: python scripts/memory/refusal_status.py --resolve N "
              "--decision {fix-policy|abandon|split|architecture} --notes \"...\"")
        print("         (add --extract-mechanism for interactive mechanism extraction)")
        return 0

    if not entries:
        print("no refusals logged")
        return 0
    print(f"total: {len(entries)}  (pending {len(pending)}, resolved {len(resolved)})\n")
    for i, e in enumerate(entries, 1):
        print(_format_entry(i, e))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
