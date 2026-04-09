#!/usr/bin/env python3
"""Prune session folders older than 6 months.

Scans .code-sessions/ for folders where the yyyymmdd prefix is older than
180 days. Works on both macOS and Linux (no GNU date dependency).

Usage:
    python3 session_prune.py [--repo-root <PATH>] [--dry-run]

Output (JSON to stdout):
    {"pruned": ["20250901-abc123", ...], "count": 2}
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path


def find_repo_root(hint: str | None = None) -> Path:
    if hint:
        return Path(hint)
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return Path(result.stdout.strip())


def prune_sessions(repo_root: Path, dry_run: bool = False) -> dict:
    sessions_dir = repo_root / ".code-sessions"
    if not sessions_dir.is_dir():
        return {"pruned": [], "count": 0}

    cutoff = (date.today() - timedelta(days=180)).strftime("%Y%m%d")
    pruned = []

    for entry in sorted(sessions_dir.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        # Skip non-session folders (e.g., "backlog", "current")
        folder_date = name[:8]
        if not folder_date.isdigit() or len(folder_date) != 8:
            continue
        if folder_date < cutoff:
            if dry_run:
                print(f"Would prune: {name}", file=sys.stderr)
            else:
                shutil.rmtree(entry)
                print(f"Pruned: {name}", file=sys.stderr)
            pruned.append(name)

    return {"pruned": pruned, "count": len(pruned)}


def main():
    parser = argparse.ArgumentParser(description="Prune old session folders")
    parser.add_argument("--repo-root", help="Repository root path")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be pruned without deleting")
    args = parser.parse_args()

    try:
        repo_root = find_repo_root(args.repo_root)
    except subprocess.CalledProcessError:
        print(json.dumps({"error": "Not a git repository"}))
        sys.exit(1)

    result = prune_sessions(repo_root, dry_run=args.dry_run)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
