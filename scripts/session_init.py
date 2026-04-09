#!/usr/bin/env python3
"""Initialize a new development session.

Handles repo root detection, session ID generation, folder creation,
.gitignore/.dockerignore updates, timestamp capture, state.json writing,
and optional backlog item linking.

Usage:
    python3 session_init.py [--backlog-item <ID_OR_TITLE>] [--repo-root <PATH>]

Exit codes:
    0 — success
    1 — fatal error (not a git repo, filesystem error)
    2 — ambiguous backlog match (JSON output includes ambiguous_matches)

Output (JSON to stdout):
    {
      "session_id": "20260409-a1b2c3",
      "session_dir": "/abs/path/.code-sessions/20260409-a1b2c3",
      "timestamp": "2026-04-09T12:00:00Z",
      "backlog_item": {"id": "abc123", "title": "...", "description": "...", "context": "..."} | null,
      "gitignore_updated": true,
      "errors": []
    }
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def find_repo_root(hint: str | None = None) -> Path:
    if hint:
        return Path(hint)
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return Path(result.stdout.strip())


def generate_session_id() -> str:
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    hex_part = os.urandom(3).hex()
    return f"{date_part}-{hex_part}"


def ensure_in_ignore_file(ignore_path: Path, entry: str) -> bool:
    """Append entry to ignore file if not already present. Returns True if modified."""
    if ignore_path.exists():
        content = ignore_path.read_text()
        if entry in content.splitlines():
            return False
    with open(ignore_path, "a") as f:
        f.write(f"{entry}\n")
    return True


def atomic_write_json(path: Path, data: dict):
    """Write JSON atomically using tmp file in same directory."""
    tmp_path = path.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.rename(tmp_path, path)


def find_backlog_item(repo_root: Path, query: str) -> list[dict]:
    """Search for backlog items by ID or title. Returns list of matches."""
    backlog_dir = repo_root / ".code-sessions" / "backlog"
    if not backlog_dir.is_dir():
        return []

    index_path = backlog_dir / "index.json"
    if not index_path.exists():
        return []

    index = json.loads(index_path.read_text())
    matches = []

    for i, item_id in enumerate(index.get("items", [])):
        item_path = backlog_dir / item_id / "item.json"
        if not item_path.exists():
            continue
        item = json.loads(item_path.read_text())

        # Exact ID match
        if item_id == query:
            return [{"id": item_id, "rank": i + 1, **item}]

        # Title match (case-insensitive substring)
        title = item.get("title", "")
        if query.lower() in title.lower():
            matches.append({"id": item_id, "rank": i + 1, **item})

    return matches


def link_backlog_item(repo_root: Path, item_id: str, session_id: str, timestamp: str):
    """Update a backlog item to in-progress status with active session."""
    item_path = repo_root / ".code-sessions" / "backlog" / item_id / "item.json"
    item = json.loads(item_path.read_text())
    item["status"] = "in-progress"
    item["active_session"] = session_id
    item["updated_at"] = timestamp
    atomic_write_json(item_path, item)


def main():
    parser = argparse.ArgumentParser(description="Initialize a new session")
    parser.add_argument("--backlog-item", help="Backlog item ID or title to link")
    parser.add_argument("--repo-root", help="Repository root path")
    args = parser.parse_args()

    errors = []

    # Find repo root
    try:
        repo_root = find_repo_root(args.repo_root)
    except subprocess.CalledProcessError:
        print(json.dumps({"error": "Not a git repository"}))
        sys.exit(1)

    # Generate session ID and timestamp
    session_id = generate_session_id()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    session_dir = repo_root / ".code-sessions" / session_id

    # Create session folder
    session_dir.mkdir(parents=True, exist_ok=True)

    # Update ignore files
    gitignore_updated = ensure_in_ignore_file(repo_root / ".gitignore", ".code-sessions/")
    dockerignore = repo_root / ".dockerignore"
    if dockerignore.exists():
        ensure_in_ignore_file(dockerignore, ".code-sessions/")

    # Handle backlog item
    backlog_item = None
    if args.backlog_item:
        matches = find_backlog_item(repo_root, args.backlog_item)
        if len(matches) == 0:
            errors.append(f"No backlog item found matching '{args.backlog_item}'")
        elif len(matches) > 1:
            # Ambiguous — return matches for the LLM to disambiguate
            print(json.dumps({
                "session_id": session_id,
                "session_dir": str(session_dir),
                "timestamp": timestamp,
                "ambiguous_matches": [
                    {"id": m["id"], "title": m.get("title", ""), "importance": m.get("importance", ""), "rank": m["rank"]}
                    for m in matches
                ],
                "errors": errors,
            }))
            sys.exit(2)
        else:
            match = matches[0]
            link_backlog_item(repo_root, match["id"], session_id, timestamp)
            backlog_item = {
                "id": match["id"],
                "title": match.get("title", ""),
                "description": match.get("description", ""),
                "context": match.get("source", {}).get("context", ""),
            }

    # Write state.json
    state = {
        "id": session_id,
        "name": None,
        "phase": "braindump",
        "prompts": [],
        "start_of_session_timestamp": timestamp,
        "start_of_implementation_timestamp": None,
        "end_of_session_timestamp": None,
        "branch": None,
        "worktree_path": None,
        "backlog_item_id": backlog_item["id"] if backlog_item else None,
    }
    atomic_write_json(session_dir / "state.json", state)

    # Output result
    print(json.dumps({
        "session_id": session_id,
        "session_dir": str(session_dir),
        "timestamp": timestamp,
        "backlog_item": backlog_item,
        "gitignore_updated": gitignore_updated,
        "errors": errors,
    }))


if __name__ == "__main__":
    main()
