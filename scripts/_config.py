"""Shared config loader for Separation & Audit scripts.

Resolution order:
    1. Explicit path argument  (passed by caller)
    2. $SAA_CONFIG environment variable
    3. architecture.config.yaml   in current working directory
    4. architecture.config.yaml   in git repo root
    5. Built-in defaults          (this module's DEFAULT_CONFIG)

Scripts should call ``load_config()`` once near the top of ``main()``:

    from _config import load_config
    cfg = load_config()
    checklist_path = cfg["policy_checklist"]

Requires PyYAML (see requirements.txt).
"""
from __future__ import annotations

import os
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Separation & Audit requires PyYAML.\n"
        "Install with:  pip install -r requirements.txt"
    ) from exc


CONFIG_FILENAME = "architecture.config.yaml"


DEFAULT_CONFIG: dict[str, Any] = {
    "policy_corpus": [
        "docs/policy.md",
        "docs/policy-supplement.md",
    ],
    "policy_checklist": "docs/policy-checklist.md",

    "audit": {
        "retry_limit": 2,
        "retry_state": ".git/cold-eyes-retry-state.json",
        "refusal_log": "docs/refusal-log.jsonl",
        "excluded_files": [
            "docs/policy.md",
            "docs/policy-supplement.md",
            "docs/policy-checklist.md",
            "docs/refusal-log.jsonl",
            "docs/mechanism-memory-schema.md",
            "docs/mechanism-memory.jsonl",
            "docs/gate-events.jsonl",
            "docs/architecture.md",
            "docs/classify-rules.md",
            "CLAUDE.md",
            "scripts/cold_eyes.py",
            "scripts/classify.py",
        ],
        "excluded_dirs": [
            ".claude/",
            "agents/",
            "scripts/",
            "docs/plans/",
        ],
    },

    "memory": {
        "mechanism_memory": "docs/mechanism-memory.jsonl",
        "mechanism_schema": "docs/mechanism-memory-schema.md",
        "decay_tau_days": 30,
    },

    "gate_events": "docs/gate-events.jsonl",

    "checklist": {
        "anchor_header_regex": r"^## (?:錨點|Anchor) (\d+)[:：]?",
        "deathline_header_regex": r"^## (?:附錄 A|Deathline)[:：]?",
        "level2_header_regex": r"^### Level 2",
        "clause_prefix": "§",
        "valid_clauses": "auto",
    },

    "pre_commit": [
        {"id": "secret_scan", "kind": "script",
         "path": "scripts/gates/secret_scan.py"},
        {"id": "code_quality", "kind": "shell", "command": ""},
        {"id": "cold_eyes", "kind": "script",
         "path": "scripts/audit/cold_eyes_gate.py"},
    ],

    "classify": {
        "path_rules": [],
        "policy_paths_exact": [],
        "policy_paths_glob": [],
        "whitelist_exact": ["CLAUDE.md", "docs/refusal-log.jsonl"],
        "whitelist_glob": ["docs/plans/*.md", ".git/**", ".claude/**"],
        "issue_type_rules": {
            "anchor-violation": ["main-agent"],
            "deathline-violation": ["main-agent"],
            "tone-drift": ["policy-guardian"],
            "logic-error": ["dev-agent"],
            "test-failure": ["dev-agent", "qa-agent"],
            "security": ["dev-agent"],
        },
    },
}


def _git_root() -> Path | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8",
        )
        if r.returncode == 0:
            return Path(r.stdout.strip())
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return None


def _find_config_file() -> Path | None:
    env = os.environ.get("SAA_CONFIG")
    if env:
        p = Path(env)
        if p.exists():
            return p

    cwd = Path.cwd() / CONFIG_FILENAME
    if cwd.exists():
        return cwd

    root = _git_root()
    if root:
        p = root / CONFIG_FILENAME
        if p.exists():
            return p

    return None


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into `base`. Lists from override replace lists in base."""
    result = deepcopy(base)
    for key, value in override.items():
        if (key in result and isinstance(result[key], dict)
                and isinstance(value, dict)):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Return merged config. Missing keys fall back to DEFAULT_CONFIG."""
    if path is None:
        resolved = _find_config_file()
    else:
        resolved = Path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Config file not found: {resolved}")

    if resolved is None:
        return deepcopy(DEFAULT_CONFIG)

    with resolved.open("r", encoding="utf-8") as f:
        user = yaml.safe_load(f) or {}

    if not isinstance(user, dict):
        raise ValueError(f"Config root must be a mapping, got {type(user)}")

    return _deep_merge(DEFAULT_CONFIG, user)


def resolve_path(cfg_value: str, repo_root: Path | None = None) -> Path:
    """Resolve a config path. Absolute paths are kept; relative paths resolve against repo root (or cwd)."""
    p = Path(cfg_value)
    if p.is_absolute():
        return p
    base = repo_root or _git_root() or Path.cwd()
    return base / p


if __name__ == "__main__":
    import json
    cfg = load_config()
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
