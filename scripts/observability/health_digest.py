#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Health Digest — one-page aggregation of observability data.

Aggregates the three append-only stores managed by the architecture:
    - refusal_log       Cold Eyes Fail#2 refusal records
    - mechanism_memory  Abstract drift-pattern memory
    - gate_events       Pre-commit layer fail events

Usage:
    python scripts/observability/health_digest.py              # full digest
    python scripts/observability/health_digest.py --since 7d   # last 7 days
    python scripts/observability/health_digest.py --since 30d
    python scripts/observability/health_digest.py --since 24h

Session-start hooks may prompt the user to run this when thresholds are crossed;
no cron needed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _config import load_config, resolve_path  # noqa: E402


def _load(path: Path) -> list[dict]:
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


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except Exception:
        return None


def _parse_since(s: str) -> datetime | None:
    """Parse '7d' / '30d' / '24h' → datetime cutoff."""
    if not s:
        return None
    m = re.match(r"^(\d+)\s*([dh])$", s.strip().lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    delta = timedelta(days=n) if unit == "d" else timedelta(hours=n)
    return datetime.now(timezone.utc) - delta


def _filter_since(entries: list[dict], cutoff: datetime | None, key: str) -> list[dict]:
    if cutoff is None:
        return entries
    out = []
    for e in entries:
        ts = _parse_iso(e.get(key, ""))
        if ts and ts >= cutoff:
            out.append(e)
    return out


def _age_str(ts: datetime) -> str:
    delta = datetime.now(timezone.utc) - ts
    if delta.days > 0:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    return "recent"


def _section_refusal(entries: list[dict]) -> None:
    print("=" * 60)
    print("Refusals")
    print("=" * 60)
    if not entries:
        print("  (empty — Cold Eyes Fail#2 has not triggered)")
        print()
        return

    pending = [e for e in entries if e.get("user_decision") is None]
    resolved = [e for e in entries if e.get("user_decision") is not None]

    print(f"total: {len(entries)}  (pending {len(pending)}, resolved {len(resolved)})")
    print()

    clauses: Counter = Counter()
    for e in entries:
        for c in e.get("policy_clauses", []):
            clauses[c] += 1
    if clauses:
        print("by policy_clause:")
        for c, n in clauses.most_common(10):
            print(f"  {c:20s} {n:4d}")
        print()

    decisions = Counter(e.get("user_decision") or "pending" for e in entries)
    print("by decision:")
    for d, n in decisions.most_common():
        print(f"  {d:20s} {n:4d}")
    print()

    if pending:
        oldest = min(pending, key=lambda e: e.get("timestamp", ""))
        ts = _parse_iso(oldest.get("timestamp", ""))
        if ts:
            print(f"oldest pending: {oldest.get('timestamp')} ({_age_str(ts)})")
            print("   resolve: python scripts/memory/refusal_status.py --resolve N ...")
    print()


def _section_mechanism(entries: list[dict]) -> None:
    print("=" * 60)
    print("Mechanism Memory")
    print("=" * 60)
    if not entries:
        print("  (empty — no mechanisms extracted yet)")
        print()
        return

    print(f"total: {len(entries)}")
    print()

    clauses = Counter(e.get("policy_clause", "?") for e in entries)
    print("by policy_clause:")
    for c, n in clauses.most_common():
        print(f"  {c:20s} {n:4d}")
    print()

    top_hit = sorted(entries, key=lambda e: e.get("hit_count", 1),
                     reverse=True)[:5]
    print("most-hit (top 5):")
    for e in top_hit:
        summary = e.get("summary", "")[:50]
        hit = e.get("hit_count", 1)
        last = _parse_iso(e.get("last_hit_at", ""))
        age = _age_str(last) if last else "?"
        print(f"  hit={hit:3d}  last={age:12s}  {summary}")
    print()

    total_hits = sum(e.get("hit_count", 1) for e in entries)
    if total_hits >= 20:
        clause_hits: Counter = Counter()
        for e in entries:
            clause_hits[e.get("policy_clause", "?")] += e.get("hit_count", 1)
        for c, n in clause_hits.most_common(1):
            if n > total_hits * 0.5:
                print(f"warn: clause {c} accumulated {n}/{total_hits} hits "
                      f"(>50%) — that anchor may be under-specified in policy")
                print()
                break


def _section_gate(entries: list[dict]) -> None:
    print("=" * 60)
    print("Gate Events (fails only)")
    print("=" * 60)
    if not entries:
        print("  (empty — no pre-commit gate has fired)")
        print()
        return

    print(f"total: {len(entries)} events")
    print()

    layers = Counter(e.get("layer", "?") for e in entries)
    print("by layer:")
    for l, n in layers.most_common():
        print(f"  {l:20s} {n:4d}")
    print()

    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = [
        e for e in entries
        if (_parse_iso(e.get("timestamp", "")) or datetime.min.replace(
            tzinfo=timezone.utc
        )) >= cutoff_24h
    ]
    if recent:
        print(f"past 24h: {len(recent)} events")
        rlayers = Counter(e.get("layer", "?") for e in recent)
        for l, n in rlayers.most_common():
            print(f"  {l:20s} {n:4d}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate refusal / mechanism / gate-events data",
    )
    parser.add_argument("--since", default=None,
                        help="Time window (e.g. 7d, 30d, 24h)")
    parser.add_argument("--config", default=None,
                        help="Path to architecture.config.yaml")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    cfg = load_config(args.config)
    cutoff = _parse_since(args.since) if args.since else None

    refusal = _load(resolve_path(cfg["audit"]["refusal_log"]))
    mech = _load(resolve_path(cfg["memory"]["mechanism_memory"]))
    gate = _load(resolve_path(cfg["gate_events"]))

    if cutoff:
        refusal = _filter_since(refusal, cutoff, "timestamp")
        mech = _filter_since(mech, cutoff, "created_at")
        gate = _filter_since(gate, cutoff, "timestamp")
        print(f"(filtering since={args.since} → cutoff {cutoff.isoformat()})\n")

    _section_refusal(refusal)
    _section_mechanism(mech)
    _section_gate(gate)

    return 0


if __name__ == "__main__":
    sys.exit(main())
