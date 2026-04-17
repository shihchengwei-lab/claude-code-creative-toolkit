#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cold Eyes Gate — retry-bounded auditor + refusal log trigger.

Chains classify.py (backward split) + cold_eyes.py + retry/refusal logic.

Flow:
  1. Run cold_eyes.py --scope staged → {pass, issues}
  2. Pass  → clear retry state, exit 0 (pre-commit allows commit)
  3. Fail#1 → run classify.py backward for dispatch hint, increment retry, exit 1
               (stderr shows issues + dispatch targets so Main Agent can fix)
  4. Fail#2 → append refusal_log, clear retry state, exit 1
               (stderr gives minimal message only — no clause/type — to prevent
                Main Agent from self-arguing against the verdict)

Retry state: branch-bound file at audit.retry_state (not committed).
             Cleared on successful commit or branch switch.

CLI:
  python scripts/audit/cold_eyes_gate.py                 # pre-commit (staged)
  python scripts/audit/cold_eyes_gate.py --scope working # dry-run check
  python scripts/audit/cold_eyes_gate.py --reset         # clear retry state

Exit codes:
  0 = pass
  1 = fail (commit blocked)
  2 = infrastructure failure

Spec: docs/architecture.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _config import load_config, resolve_path  # noqa: E402


GATE_DIR = Path(__file__).resolve().parent


# ---- Primitives ----
def _run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", **kw,
    )


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root() -> Path:
    r = _run(["git", "rev-parse", "--show-toplevel"])
    if r.returncode != 0:
        print("cold-eyes-gate: not inside a git repo", file=sys.stderr)
        sys.exit(2)
    return Path(r.stdout.strip())


def _current_branch() -> str:
    r = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return r.stdout.strip() if r.returncode == 0 else "HEAD-detached"


def _head_sha() -> str:
    r = _run(["git", "rev-parse", "HEAD"])
    return r.stdout.strip() if r.returncode == 0 else "NO-HEAD"


def _staged_files() -> list[str]:
    r = _run(["git", "diff", "--cached", "--name-only"])
    return [f for f in r.stdout.splitlines() if f]


def _staged_diff_hash() -> str:
    r = _run(["git", "diff", "--cached"])
    return hashlib.sha256(r.stdout.encode("utf-8")).hexdigest()


# ---- Retry state ----
def _load_state(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _clear_state(path: Path) -> None:
    if path.exists():
        path.unlink()


# ---- Subprocess calls ----
def _run_cold_eyes(repo: Path, scope: str, config: str | None) -> dict:
    script = GATE_DIR / "cold_eyes.py"
    cmd = [sys.executable, str(script), "--scope", scope]
    if config:
        cmd.extend(["--config", config])
    r = _run(cmd, cwd=str(repo))
    if r.returncode not in (0, 1):
        print(f"cold-eyes-gate: cold_eyes.py failed — {r.stderr.strip()}",
              file=sys.stderr)
        sys.exit(2)
    try:
        return json.loads(r.stdout.strip())
    except json.JSONDecodeError:
        print(f"cold-eyes-gate: cold_eyes.py non-JSON output — {r.stdout[:200]}",
              file=sys.stderr)
        sys.exit(2)


def _run_classify_backward(issues: list[dict], config: str | None) -> list[dict]:
    script = GATE_DIR / "classify.py"
    cmd = [sys.executable, str(script), "backward",
           "--issues", json.dumps(issues, ensure_ascii=False)]
    if config:
        cmd.extend(["--config", config])
    r = _run(cmd)
    if r.returncode != 0:
        return []
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return []


# ---- Refusal log ----
def _append_refusal(log_path: Path, issues: list[dict], retry_count: int) -> dict:
    """Append a refusal entry. Schema: see docs/refusal-spec.md."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    branch = _current_branch()
    task_id = branch if branch and branch != "HEAD-detached" else _head_sha()
    entry = {
        "timestamp": _iso_utc_now(),
        "task_id": task_id,
        "output_artifact": {
            "diff_hash": _staged_diff_hash(),
            "files": _staged_files(),
        },
        "policy_clauses": sorted({i["policy_clause"] for i in issues}),
        "issue_types": sorted({i["type"] for i in issues}),
        "retry_count": retry_count,
        "user_decision": None,
        "user_decision_notes": None,
        "resolved_at": None,
    }
    with log_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


# ---- Message formatting ----
def _fail_first_message(issues: list[dict], dispatch: list[dict]) -> str:
    lines = ["cold-eyes: #1 fail — commit not created"]
    lines.append("issues:")
    for i in issues:
        lines.append(f"  {i['policy_clause']} / {i['type']}")
    if dispatch:
        targets = sorted({t for d in dispatch for t in d.get("dispatch", [])})
        if targets:
            lines.append(f"dispatch → {', '.join(targets)}")
    lines.append("Fix and recommit. If Fail#2, a refusal entry is written (no further hints).")
    return "\n".join(lines)


# ---- Main ----
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cold Eyes Gate — retry-bounded audit + refusal log",
    )
    parser.add_argument("--scope", default="staged",
                        choices=["staged", "working", "head"],
                        help="cold_eyes scope (default: staged, used by pre-commit)")
    parser.add_argument("--reset", action="store_true",
                        help="Clear retry state and exit")
    parser.add_argument("--config", default=None,
                        help="Path to architecture.config.yaml")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    cfg = load_config(args.config)
    repo = _repo_root()
    state_file = resolve_path(cfg["audit"]["retry_state"], repo)
    refusal_log = resolve_path(cfg["audit"]["refusal_log"], repo)
    retry_limit = int(cfg["audit"]["retry_limit"])

    if args.reset:
        _clear_state(state_file)
        print("cold-eyes-gate: retry state cleared")
        return 0

    # 1. Run Cold Eyes
    result = _run_cold_eyes(repo, args.scope, args.config)
    passed = bool(result.get("pass", False))
    issues = result.get("issues", [])

    # 2. Pass → clear state, allow
    if passed:
        _clear_state(state_file)
        return 0

    # 3. Fail path — load retry state
    state = _load_state(state_file)
    branch = _current_branch()
    count = 0
    if state and state.get("branch") == branch:
        count = int(state.get("count", 0))

    # 4. Fail#1 — give Main Agent one chance to fix
    if count < retry_limit - 1:
        dispatch = _run_classify_backward(issues, args.config)
        _save_state(state_file, {
            "branch": branch,
            "count": count + 1,
            "first_fail_at": _iso_utc_now(),
            "diff_hash": _staged_diff_hash(),
        })
        print(_fail_first_message(issues, dispatch), file=sys.stderr)
        return 1

    # 5. Fail#2 — append refusal, clear state, minimal message
    _append_refusal(refusal_log, issues, retry_count=retry_limit)
    _clear_state(state_file)
    print("cold-eyes: commit deferred — refusal logged, awaiting user resolution",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
