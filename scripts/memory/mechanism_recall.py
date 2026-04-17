#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mechanism Recall — retrieve relevant drift patterns from mechanism memory.

Schema: docs/mechanism-memory-schema.md

White-bear firewall (architecture invariant):
    Only the Policy layer (policy-guardian) and the Audit layer (cold_eyes)
    may read the `summary` field. Reasoning-layer agents MUST NOT access this
    store. The `positive_rewrite` field is the only version safe for Reasoning.

Usage:
    python scripts/memory/mechanism_recall.py --text "<content under review>" \\
        [--tags tag1,tag2] [--top-n N]

Scoring:
    - Keyword hit (substring match in --text):  +2 per occurrence
    - Tag intersection:                          +3 per match
    - last_hit_at exponential decay (tau = 30d): multiplier in [0.5, 1.0]

Side effect:
    For each returned entry, in-place increments hit_count +1 and refreshes
    last_hit_at to now. Uses atomic rewrite (.tmp → rename) to prevent corruption.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _config import load_config, resolve_path  # noqa: E402


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str) -> float:
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        ).timestamp()
    except Exception:
        return 0.0


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                print(
                    f"mechanism_recall: skipped unparsable line: {line[:60]}",
                    file=sys.stderr,
                )
    return items


def _score(mech: dict, text: str, query_tags: set[str], tau_seconds: float) -> float:
    score = 0.0

    for kw in mech.get("keywords", []):
        if not kw:
            continue
        score += 2.0 * text.count(kw)

    mech_tags = set(mech.get("tags", []))
    if query_tags and mech_tags:
        score += 3.0 * len(query_tags & mech_tags)

    last_hit = _parse_iso(mech.get("last_hit_at", ""))
    if last_hit > 0:
        age = max(0.0, time.time() - last_hit)
        decay = math.exp(-age / tau_seconds)
        score *= 0.5 + 0.5 * decay  # weight in [0.5, 1.0]

    return score


def _save_atomic(path: Path, items: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mechanism Recall — retrieve drift-pattern memory",
    )
    parser.add_argument("--text", required=True,
                        help="Content under review (used for keyword matching)")
    parser.add_argument("--tags", default="",
                        help="Comma-separated expected tags (boosts scoring)")
    parser.add_argument("--top-n", type=int, default=3,
                        help="Return top-N entries (default: 3)")
    parser.add_argument("--jsonl", default=None,
                        help="Override memory.mechanism_memory path from config")
    parser.add_argument("--no-update", action="store_true",
                        help="Dry-run: don't update hit_count / last_hit_at")
    parser.add_argument("--config", default=None,
                        help="Path to architecture.config.yaml")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    cfg = load_config(args.config)
    jsonl_path = Path(args.jsonl) if args.jsonl else resolve_path(
        cfg["memory"]["mechanism_memory"]
    )
    tau_seconds = float(cfg["memory"]["decay_tau_days"]) * 24 * 3600

    items = _load(jsonl_path)
    if not items:
        # Empty store is normal (fresh install). Not an error.
        print("[]")
        return 0

    query_tags = {t.strip() for t in args.tags.split(",") if t.strip()}
    scored = [(_score(m, args.text, query_tags, tau_seconds), m) for m in items]
    scored.sort(key=lambda x: x[0], reverse=True)

    top = [(s, m) for s, m in scored if s > 0][: args.top_n]

    result = []
    updated_ids = set()
    now = _iso_now()

    for score, mech in top:
        result.append({
            "id": mech["id"],
            "summary": mech["summary"],
            "positive_rewrite": mech.get("positive_rewrite", ""),
            "policy_clause": mech.get("policy_clause", ""),
            "hit_count": mech.get("hit_count", 1),
            "score": round(score, 2),
        })
        updated_ids.add(mech["id"])

    if not args.no_update and updated_ids:
        for mech in items:
            if mech["id"] in updated_ids:
                mech["hit_count"] = mech.get("hit_count", 1) + 1
                mech["last_hit_at"] = now
        _save_atomic(jsonl_path, items)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
