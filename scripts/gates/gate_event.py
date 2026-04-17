#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gate Event Logger — minimal append-only recorder.

Called by pre-commit when any gate fails (secret_scan, code_quality, cold_eyes).
Appends one JSONL line to gate_events log for later analysis.

Entry schema:
    {"timestamp": "ISO-8601 UTC", "layer": "<layer_id>", "decision": "fail", "files": [...]}

CLI:
    python scripts/gates/gate_event.py --layer secret_scan --decision fail --files "a.py b.py"

No analysis, no dashboard, no rotation — append and let observability scripts read.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _config import load_config, resolve_path  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Append one event to gate_events log"
    )
    parser.add_argument("--layer", required=True,
                        help="Gate layer id (e.g. secret_scan, code_quality, cold_eyes)")
    parser.add_argument("--decision", required=True,
                        help="Outcome (e.g. fail, fail_1, fail_2)")
    parser.add_argument("--files", default="",
                        help="Whitespace-separated file list")
    parser.add_argument("--config", default=None,
                        help="Path to architecture.config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    log_path = resolve_path(cfg["gate_events"])

    files = [f for f in args.files.split() if f]
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "layer": args.layer,
        "decision": args.decision,
        "files": files,
    }

    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"gate_event: write failed — {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
