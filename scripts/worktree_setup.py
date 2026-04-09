#!/usr/bin/env python3
"""Set up a git worktree for a session.

Handles branch uniqueness, worktree creation, .worktreeinclude file copying,
session symlink, dependency detection, and state.json update.

Usage:
    python3 worktree_setup.py --session-id <ID> --branch <NAME> --name <NAME> [--repo-root <PATH>]

Exit codes:
    0 — success
    1 — fatal error

Output (JSON to stdout):
    {
      "branch": "add-retry-logic",
      "worktree_path": "/abs/path/.claude/worktrees/add-retry-logic",
      "branch_renamed": false,
      "original_branch": "add-retry-logic",
      "worktreeinclude_copied": [".env", "data/"],
      "worktreeinclude_skipped": [".legacy_env"],
      "dependency_manager": "uv",
      "dependency_install_cmd": "cd ... && uv sync",
      "session_state_updated": true,
      "errors": []
    }
"""

import argparse
import json
import os
import shutil
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


def atomic_write_json(path: Path, data: dict):
    tmp_path = path.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.rename(tmp_path, path)


def ensure_unique_branch(name: str) -> str:
    """Find a unique branch name, appending -2, -3, etc. if needed."""
    candidate = name
    suffix = 1
    while True:
        result = subprocess.run(
            ["git", "branch", "--list", candidate],
            capture_output=True, text=True,
        )
        if not result.stdout.strip():
            return candidate
        suffix += 1
        candidate = f"{name}-{suffix}"


def ensure_gitignored(repo_root: Path, entry: str):
    gitignore = repo_root / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if entry in content.splitlines():
            return
    with open(gitignore, "a") as f:
        f.write(f"{entry}\n")


def process_worktreeinclude(repo_root: Path, worktree_path: Path) -> tuple[list[str], list[str]]:
    """Copy files listed in .worktreeinclude from main repo to worktree.

    Returns (copied, skipped) lists.
    """
    include_file = repo_root / ".worktreeinclude"
    if not include_file.exists():
        return [], []

    copied = []
    skipped = []

    for line in include_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        src = repo_root / line
        dst = worktree_path / line

        if not src.exists():
            skipped.append(line)
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        copied.append(line)

    return copied, skipped


def detect_dependency_manager(worktree_path: Path) -> tuple[str | None, str | None]:
    """Detect dependency manager and return (name, install_command)."""
    if (worktree_path / "uv.lock").exists():
        return "uv", f'cd "{worktree_path}" && uv sync'
    if (worktree_path / "package-lock.json").exists():
        return "npm", f'cd "{worktree_path}" && npm ci'
    if (worktree_path / "yarn.lock").exists():
        return "yarn", f'cd "{worktree_path}" && yarn install --frozen-lockfile'
    return None, None


def main():
    parser = argparse.ArgumentParser(description="Set up a session worktree")
    parser.add_argument("--session-id", required=True, help="Session ID")
    parser.add_argument("--branch", required=True, help="Desired branch name")
    parser.add_argument("--name", required=True, help="Session name")
    parser.add_argument("--repo-root", help="Repository root path")
    args = parser.parse_args()

    errors = []

    try:
        repo_root = find_repo_root(args.repo_root)
    except subprocess.CalledProcessError:
        print(json.dumps({"error": "Not a git repository"}))
        sys.exit(1)

    # Ensure unique branch name
    original_branch = args.branch
    branch = ensure_unique_branch(original_branch)
    branch_renamed = branch != original_branch

    # Ensure .claude/worktrees/ is gitignored
    ensure_gitignored(repo_root, ".claude/worktrees/")

    # Create worktree
    worktree_path = repo_root / ".claude" / "worktrees" / branch
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "-b", branch],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(json.dumps({"error": f"Failed to create worktree: {result.stderr.strip()}"}))
        sys.exit(1)
    print(f"Created worktree at {worktree_path}", file=sys.stderr)

    # Process .worktreeinclude
    copied, skipped = process_worktreeinclude(repo_root, worktree_path)

    # Symlink session folder
    sessions_dir = worktree_path / ".code-sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    current_link = sessions_dir / "current"
    session_source = repo_root / ".code-sessions" / args.session_id
    if current_link.exists() or current_link.is_symlink():
        current_link.unlink()
    current_link.symlink_to(session_source)

    # Detect dependency manager
    dep_manager, dep_cmd = detect_dependency_manager(worktree_path)

    # Update state.json
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state_file = session_source / "state.json"
    state_updated = False
    if state_file.exists():
        state = json.loads(state_file.read_text())
        state["name"] = args.name
        state["branch"] = branch
        state["worktree_path"] = f".claude/worktrees/{branch}"
        state["phase"] = "implementing"
        state["start_of_implementation_timestamp"] = timestamp
        atomic_write_json(state_file, state)
        state_updated = True
    else:
        errors.append(f"state.json not found at {state_file}")

    # Output result
    print(json.dumps({
        "branch": branch,
        "worktree_path": str(worktree_path),
        "branch_renamed": branch_renamed,
        "original_branch": original_branch,
        "worktreeinclude_copied": copied,
        "worktreeinclude_skipped": skipped,
        "dependency_manager": dep_manager,
        "dependency_install_cmd": dep_cmd,
        "session_state_updated": state_updated,
        "errors": errors,
    }))


if __name__ == "__main__":
    main()
