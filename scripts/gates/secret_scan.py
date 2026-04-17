#!/usr/bin/env python3
"""Secret Scanner — pre-commit Layer 0.

Scans staged diff added lines ('+' prefix) for obvious secret/token leaks.
Matches well-known prefix patterns only; no fuzzy detection, zero-false-positive priority.

Usage:
    python scripts/gates/secret_scan.py                    # scan staged diff (pre-commit)
    python scripts/gates/secret_scan.py --diff path.diff   # from file
    git log -p --all | python scripts/gates/secret_scan.py --diff -   # full history audit
"""
from __future__ import annotations

import re
import subprocess
import sys

# Exclude self — the patterns are part of this file's source.
EXCLUDE_FILES = {
    "scripts/gates/secret_scan.py",
    "scripts/secret_scan.py",  # legacy path (pre-restructure)
}

# (name, regex, description)
# All well-known prefixes only. Generic "password=" scans avoided to prevent noise.
PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "supabase-jwt",
        re.compile(r'(SERVICE_ROLE|ANON_KEY|service_role|anon)["\']?\s*[:=]\s*["\']eyJ[A-Za-z0-9_-]{20,}'),
        "Supabase JWT (service_role / anon key)",
    ),
    (
        "github-pat",
        re.compile(r"ghp_[A-Za-z0-9]{36,}"),
        "GitHub Personal Access Token",
    ),
    (
        "github-oauth",
        re.compile(r"gho_[A-Za-z0-9]{36,}"),
        "GitHub OAuth Token",
    ),
    (
        "github-app",
        re.compile(r"ghs_[A-Za-z0-9]{36,}"),
        "GitHub App Token",
    ),
    (
        "openai-key",
        re.compile(r"sk-(proj-)?[A-Za-z0-9]{40,}"),
        "OpenAI API Key",
    ),
    (
        "anthropic-key",
        re.compile(r"sk-ant-api\d{2}-[A-Za-z0-9_-]{80,}"),
        "Anthropic API Key",
    ),
    (
        "aws-access-key",
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "AWS Access Key ID",
    ),
    (
        "private-key-pem",
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        "PEM Private Key",
    ),
    (
        "bearer-token",
        re.compile(r"[Bb]earer\s+[A-Za-z0-9._~+/=-]{40,}"),
        "Bearer Token (length >= 40)",
    ),
]


def get_staged_diff() -> str:
    r = subprocess.run(
        ["git", "diff", "--cached", "--unified=0"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return r.stdout


def parse_diff(diff: str) -> list[tuple[str, int, str]]:
    """Return [(filepath, line_no, content)] for '+' added lines only."""
    results: list[tuple[str, int, str]] = []
    current_file: str | None = None
    current_line = 0

    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            current_file = raw[6:]
            current_line = 0
        elif raw.startswith("+++ "):
            current_file = None
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            if m:
                current_line = int(m.group(1)) - 1
        elif raw.startswith("+") and not raw.startswith("+++"):
            current_line += 1
            if current_file and current_file not in EXCLUDE_FILES:
                results.append((current_file, current_line, raw[1:]))
        elif raw.startswith(" "):
            current_line += 1

    return results


def scan(lines: list[tuple[str, int, str]]) -> list[tuple[str, int, str, str]]:
    """Return [(filepath, line_no, pattern_name, sample)]."""
    hits: list[tuple[str, int, str, str]] = []
    for filepath, line_no, content in lines:
        for name, pattern, _desc in PATTERNS:
            m = pattern.search(content)
            if m:
                sample = m.group(0)
                if len(sample) > 40:
                    sample = sample[:20] + "..." + sample[-8:]
                hits.append((filepath, line_no, name, sample))
    return hits


def main() -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Scan diff added lines for well-known secret/token prefixes"
    )
    parser.add_argument("--diff", default=None,
                        help="Read diff from file ('-' for stdin). Overrides staged default.")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    if args.diff:
        if args.diff == "-":
            diff = sys.stdin.read()
        else:
            diff = Path(args.diff).read_text(encoding="utf-8", errors="replace")
    else:
        diff = get_staged_diff()

    if not diff.strip():
        return 0

    lines = parse_diff(diff)
    hits = scan(lines)

    if not hits:
        return 0

    print("Secret scan blocked: suspected secret/token detected", file=sys.stderr)
    print("", file=sys.stderr)
    for filepath, line_no, name, sample in hits:
        print(f"  {filepath}:{line_no}  [{name}]  {sample}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Resolution:", file=sys.stderr)
    print("  1. Real secret — rotate now (revoke + reissue), use env vars in code", file=sys.stderr)
    print("  2. Test fixture — replace with obvious fake (e.g. 'xxx' or 'REDACTED')", file=sys.stderr)
    print("  3. False positive — add filepath to EXCLUDE_FILES in this script", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
