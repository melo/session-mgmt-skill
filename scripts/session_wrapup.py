#!/usr/bin/env python3
"""Generate implementation report and prepare session for merging.

Records end timestamp, computes time breakdown, collects commits, derives
GitHub URL, generates the implementation report markdown, sets phase to
"done", and copies state.json to docs.

Usage:
    python3 session_wrapup.py --session-dir <PATH> [--repo-root <PATH>]

Exit codes:
    0 — success
    1 — fatal error

Output (JSON to stdout):
    {
      "report_path": "docs/implementation/.../impl-report.md",
      "state_copy_path": "docs/implementation/.../state.json",
      "docs_dir": "docs/implementation/...",
      "end_timestamp": "2026-04-09T14:00:00Z",
      "planning_time": "0h 30m",
      "implementation_time": "1h 30m",
      "total_time": "2h 0m",
      "commit_count": 8,
      "branch": "add-retry-logic",
      "github_url": "https://github.com/owner/repo",
      "errors": []
    }
"""

import argparse
import json
import os
import re
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


def format_duration(start_iso: str | None, end_iso: str | None) -> str:
    """Format duration between two ISO timestamps as 'Xh Ym'."""
    if not start_iso or not end_iso:
        return "N/A"
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        delta = end - start
        total_minutes = int(delta.total_seconds() / 60)
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours}h {minutes}m"
    except (ValueError, TypeError):
        return "N/A"


def parse_github_url(remote_url: str) -> str | None:
    """Parse git remote URL to GitHub HTTPS URL."""
    if not remote_url:
        return None

    # SSH format: git@github.com:owner/repo.git
    ssh_match = re.match(r"git@github\.com:(.+?)(?:\.git)?$", remote_url)
    if ssh_match:
        return f"https://github.com/{ssh_match.group(1)}"

    # HTTPS format: https://github.com/owner/repo.git
    https_match = re.match(r"https://github\.com/(.+?)(?:\.git)?$", remote_url)
    if https_match:
        return f"https://github.com/{https_match.group(1)}"

    return None


def collect_commits(branch: str) -> list[dict]:
    """Collect commits on branch since diverging from main."""
    result = subprocess.run(
        ["git", "log", f"main..{branch}", "--format=%H %s"],
        capture_output=True, text=True,
    )
    commits = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split(" ", 1)
        commits.append({"hash": parts[0], "message": parts[1] if len(parts) > 1 else ""})
    return commits


def generate_report(
    session_name: str,
    session_id: str,
    branch: str,
    worktree_path: str,
    planning_time: str,
    impl_time: str,
    total_time: str,
    commits: list[dict],
    github_url: str | None,
) -> str:
    """Generate the implementation report markdown."""
    lines = [
        f"# Implementation Report \u2014 {session_name}",
        "",
        "| Item | Value |",
        "|------|-------|",
        f"| **Session ID** | `{session_id}` |",
        f"| **Session folder** | `.code-sessions/{session_id}` |",
        f"| **Branch** | `{branch}` |",
        f"| **Worktree** | `{worktree_path}` |",
        f"| **Planning time** | {planning_time} |",
        f"| **Implementation time** | {impl_time} |",
        f"| **Total session time** | {total_time} |",
        f"| **Commits** | {len(commits)} |",
        "",
        "## Commits",
        "",
        "| Hash | Message |",
        "|------|---------|",
    ]

    for commit in commits:
        short_hash = commit["hash"][:7]
        if github_url:
            hash_link = f"[`{short_hash}`]({github_url}/commit/{commit['hash']})"
        else:
            hash_link = f"`{short_hash}`"
        lines.append(f"| {hash_link} | {commit['message']} |")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate session implementation report")
    parser.add_argument("--session-dir", required=True, help="Path to session directory")
    parser.add_argument("--repo-root", help="Repository root path")
    args = parser.parse_args()

    errors = []

    try:
        repo_root = find_repo_root(args.repo_root)
    except subprocess.CalledProcessError:
        print(json.dumps({"error": "Not a git repository"}))
        sys.exit(1)

    session_dir = Path(args.session_dir)
    state_file = session_dir / "state.json"

    if not state_file.exists():
        print(json.dumps({"error": f"state.json not found at {state_file}"}))
        sys.exit(1)

    state = json.loads(state_file.read_text())
    session_id = state["id"]
    session_name = state.get("name", session_id)
    branch = state.get("branch", "unknown")
    worktree_path = state.get("worktree_path", "")

    # Record end timestamp
    end_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state["end_of_session_timestamp"] = end_ts

    # Compute time breakdown
    planning_time = format_duration(
        state.get("start_of_session_timestamp"),
        state.get("start_of_implementation_timestamp"),
    )
    impl_time = format_duration(
        state.get("start_of_implementation_timestamp"),
        end_ts,
    )
    total_time = format_duration(
        state.get("start_of_session_timestamp"),
        end_ts,
    )

    # Set phase to done (before copying to docs)
    state["phase"] = "done"
    atomic_write_json(state_file, state)

    # Collect commits
    commits = collect_commits(branch)

    # Derive GitHub URL
    remote_result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True, text=True,
    )
    github_url = parse_github_url(remote_result.stdout.strip()) if remote_result.returncode == 0 else None

    # Determine docs directory
    date_prefix = state.get("start_of_session_timestamp", "")[:10].replace("-", "")
    docs_dir_name = f"{date_prefix}-{session_name}" if date_prefix else session_name
    docs_dir = repo_root / "docs" / "implementation" / docs_dir_name

    # Generate report
    report_content = generate_report(
        session_name, session_id, branch, worktree_path,
        planning_time, impl_time, total_time, commits, github_url,
    )
    report_filename = f"{docs_dir_name}-impl-report.md"
    report_path = docs_dir / report_filename
    docs_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_content)
    print(f"Wrote report: {report_path}", file=sys.stderr)

    # Copy state.json to docs
    state_copy_path = docs_dir / "state.json"
    shutil.copy2(state_file, state_copy_path)
    print(f"Copied state.json to {state_copy_path}", file=sys.stderr)

    # Output result
    print(json.dumps({
        "report_path": str(report_path.relative_to(repo_root)),
        "state_copy_path": str(state_copy_path.relative_to(repo_root)),
        "docs_dir": str(docs_dir.relative_to(repo_root)),
        "end_timestamp": end_ts,
        "planning_time": planning_time,
        "implementation_time": impl_time,
        "total_time": total_time,
        "commit_count": len(commits),
        "branch": branch,
        "github_url": github_url,
        "errors": errors,
    }))


if __name__ == "__main__":
    main()
