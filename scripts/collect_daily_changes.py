"""Collect daily change data and produce near-complete changelog documents.

Runs all mechanical work for the /daily-changes skill: git data collection,
session parsing, category assignment, SVG timeline generation, and markdown
table formatting. Outputs one data file per date with placeholder markers
where inference adds narrative summaries.

Usage:
    python collect_daily_changes.py                          # catch-up mode
    python collect_daily_changes.py 2026-02-20               # single date
    python collect_daily_changes.py --from 2026-02-18 --to 2026-02-20  # range
    python collect_daily_changes.py 2026-02-20 --repo-root /workspace
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape


# ── Data structures ──────────────────────────────────────────────


@dataclass
class CommitRecord:
    """A single git commit with parsed metadata."""

    hash: str
    timestamp: datetime
    subject: str  # first line of commit message
    full_message: str  # complete commit message
    files: list[FileChange] = field(default_factory=list)
    stat_text: str = ""  # git --stat output for this commit
    categories: list[str] = field(default_factory=list)
    merge_session: str | None = None  # branch name if part of a merge session

    @property
    def time_str(self) -> str:
        return self.timestamp.strftime("%H:%M")

    @property
    def code_added(self) -> int:
        return sum(f.added for f in self.files if not f.is_doc and not f.is_excluded)

    @property
    def code_removed(self) -> int:
        return sum(
            f.removed for f in self.files if not f.is_doc and not f.is_excluded
        )

    @property
    def doc_added(self) -> int:
        return sum(f.added for f in self.files if f.is_doc and not f.is_excluded)

    @property
    def doc_removed(self) -> int:
        return sum(f.removed for f in self.files if f.is_doc and not f.is_excluded)

    @property
    def total_added(self) -> int:
        return sum(f.added for f in self.files if not f.is_excluded)

    @property
    def total_removed(self) -> int:
        return sum(f.removed for f in self.files if not f.is_excluded)


@dataclass
class FileChange:
    """A single file changed in a commit."""

    path: str
    added: int
    removed: int

    @property
    def is_doc(self) -> bool:
        return self.path.startswith("docs/")

    @property
    def is_excluded(self) -> bool:
        excluded_prefixes = ("docs/db_schema/",)
        return any(self.path.startswith(p) for p in excluded_prefixes)


@dataclass
class SessionRecord:
    """A code session from state.json."""

    id: str
    name: str | None
    branch: str | None
    start: datetime | None
    impl_start: datetime | None
    end: datetime | None
    phase: str = "done"  # "done", "cancelled", etc.

    @property
    def planning_minutes(self) -> float | None:
        if self.start and self.impl_start:
            return (self.impl_start - self.start).total_seconds() / 60.0
        return None

    @property
    def impl_minutes(self) -> float | None:
        if self.impl_start and self.end:
            return (self.end - self.impl_start).total_seconds() / 60.0
        return None

    @property
    def total_minutes(self) -> float | None:
        if self.start and self.end:
            return (self.end - self.start).total_seconds() / 60.0
        return None

    @property
    def time_column(self) -> str:
        planning = self.planning_minutes
        impl = self.impl_minutes
        total = self.total_minutes
        if planning is not None and impl is not None and total is not None:
            return (
                f"{format_duration_m(planning)} + {format_duration_m(impl)}"
                f" = {format_duration_m(total)}"
            )
        if total is not None and self.impl_start is None:
            return f"{format_duration_m(total)} (no implementation phase)"
        return "—"


@dataclass
class CategoryGroup:
    """A group of commits under one category + sub-group heading."""

    category: str  # top-level category (e.g. "APIs")
    sub_group: str  # sub-group heading (e.g. "APIs — Trusted Caller Registration")
    commits: list[CommitRecord] = field(default_factory=list)

    @property
    def total_added(self) -> int:
        return sum(c.total_added for c in self.commits)

    @property
    def total_removed(self) -> int:
        return sum(c.total_removed for c in self.commits)


@dataclass
class TimeMetrics:
    """Three time metrics computed from session data."""

    daily_span: timedelta | None  # earliest start → latest end
    daily_span_start: str | None  # HH:MM
    daily_span_end: str | None  # HH:MM
    total_work: timedelta | None  # sum of individual session durations
    active_time: timedelta | None  # merged intervals

    # Fallback from commits when no sessions
    commit_span_start: str | None = None
    commit_span_end: str | None = None
    commit_span: timedelta | None = None


@dataclass
class DateData:
    """All collected data for a single date."""

    target_date: date
    is_draft: bool
    commits: list[CommitRecord]
    sessions: list[SessionRecord]
    metrics: TimeMetrics
    category_groups: list[CategoryGroup]
    merge_branches: list[str]
    svg_path: Path | None
    github_url: str
    repo_root: Path | None = None
    language: str = "en"
    primary_category: str = ""

    @property
    def code_added(self) -> int:
        return sum(c.code_added for c in self.commits)

    @property
    def code_removed(self) -> int:
        return sum(c.code_removed for c in self.commits)

    @property
    def doc_added(self) -> int:
        return sum(c.doc_added for c in self.commits)

    @property
    def doc_removed(self) -> int:
        return sum(c.doc_removed for c in self.commits)

    @property
    def code_commits(self) -> int:
        """Commits that touch at least one non-doc, non-excluded file."""
        return sum(
            1
            for c in self.commits
            if any(not f.is_doc and not f.is_excluded for f in c.files)
        )

    @property
    def yyyymmdd(self) -> str:
        return self.target_date.strftime("%Y%m%d")

    @property
    def yyyy(self) -> str:
        return self.target_date.strftime("%Y")

    @property
    def iso_date(self) -> str:
        return self.target_date.isoformat()


# ── Duration formatting ──────────────────────────────────────────


def format_duration_m(minutes: float) -> str:
    """Format minutes as Xm, XhYm, or XdYhZm."""
    m = int(minutes)
    if m < 60:
        return f"{m}m"
    if m < 48 * 60:
        h, rm = divmod(m, 60)
        return f"{h}h{rm}m"
    d, rem = divmod(m, 24 * 60)
    h, rm = divmod(rem, 60)
    return f"{d}d{h}h{rm}m"


def format_duration_td(td: timedelta) -> str:
    """Format a timedelta using format_duration_m."""
    return format_duration_m(td.total_seconds() / 60.0)


def format_number(n: int) -> str:
    """Format a number with comma separators."""
    return f"{n:,}"


# ── Timestamp parsing ────────────────────────────────────────────


def parse_ts(ts_str: str | None) -> datetime | None:
    """Parse an ISO timestamp string to datetime."""
    if not ts_str:
        return None
    ts_str = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(ts_str)


# ── Git data collection ─────────────────────────────────────────


def derive_github_url(repo_root: Path) -> str:
    """Get GitHub HTTPS URL from git remote origin."""
    try:
        url = run_git(repo_root, ["remote", "get-url", "origin"]).strip()
        url = re.sub(r"git@github\.com:", "https://github.com/", url)
        url = re.sub(r"\.git$", "", url)
        return url
    except subprocess.CalledProcessError:
        return ""


def run_git(repo_root: Path, args: list[str]) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git", "-C", str(repo_root)] + args,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def collect_commits(repo_root: Path, target_date: date) -> list[CommitRecord]:
    """Collect all commits for a given date with numstat and stat data."""
    date_str = target_date.isoformat()
    since = f"{date_str}T00:00:00"
    until = f"{date_str}T23:59:59"

    # Collect numstat data (for line counts per file)
    try:
        numstat_output = run_git(
            repo_root,
            [
                "log",
                "--numstat",
                "--format=COMMIT:%h|%aI|%s",
                f"--since={since}",
                f"--until={until}",
                "--all",
            ],
        )
    except subprocess.CalledProcessError:
        return []

    if not numstat_output.strip():
        return []

    # Collect stat data (for diffstat display)
    try:
        stat_output = run_git(
            repo_root,
            [
                "log",
                "--stat",
                "--format=COMMIT:%h|%aI|%s",
                f"--since={since}",
                f"--until={until}",
                "--all",
            ],
        )
    except subprocess.CalledProcessError:
        stat_output = ""

    # Collect full commit messages
    try:
        full_msg_output = run_git(
            repo_root,
            [
                "log",
                "--format=COMMITMSG:%h%n%B%nENDMSG",
                f"--since={since}",
                f"--until={until}",
                "--all",
            ],
        )
    except subprocess.CalledProcessError:
        full_msg_output = ""

    # Parse numstat
    commits = _parse_numstat(numstat_output)

    # Parse stat and attach
    stat_map = _parse_stat(stat_output)
    for c in commits:
        c.stat_text = stat_map.get(c.hash, "")

    # Parse full messages and attach
    msg_map = _parse_full_messages(full_msg_output)
    for c in commits:
        c.full_message = msg_map.get(c.hash, c.subject)

    # Assign merge sessions using git ancestry
    _assign_merge_sessions(commits, repo_root)

    # Sort by timestamp (earliest first)
    commits.sort(key=lambda c: c.timestamp)

    return commits


def _parse_numstat(output: str) -> list[CommitRecord]:
    """Parse git log --numstat output into CommitRecord objects."""
    commits: list[CommitRecord] = []
    current: CommitRecord | None = None

    for line in output.splitlines():
        if line.startswith("COMMIT:"):
            parts = line[7:].split("|", 2)
            if len(parts) < 3:
                continue
            hash_, iso_ts, subject = parts
            ts = parse_ts(iso_ts)
            if ts is None:
                continue
            current = CommitRecord(
                hash=hash_.strip(),
                timestamp=ts,
                subject=subject.strip(),
                full_message=subject.strip(),
            )
            commits.append(current)
        elif current and "\t" in line:
            parts = line.split("\t", 2)
            if len(parts) == 3:
                added_str, removed_str, filepath = parts
                # Binary files show "-"
                if added_str == "-" or removed_str == "-":
                    continue
                try:
                    current.files.append(
                        FileChange(
                            path=filepath.strip(),
                            added=int(added_str),
                            removed=int(removed_str),
                        )
                    )
                except ValueError:
                    continue

    return commits


def _parse_stat(output: str) -> dict[str, str]:
    """Parse git log --stat output, keyed by commit hash."""
    result: dict[str, str] = {}
    current_hash: str | None = None
    current_lines: list[str] = []

    for line in output.splitlines():
        if line.startswith("COMMIT:"):
            if current_hash and current_lines:
                result[current_hash] = "\n".join(current_lines)
            parts = line[7:].split("|", 2)
            current_hash = parts[0].strip() if parts else None
            current_lines = []
        elif current_hash:
            current_lines.append(line)

    if current_hash and current_lines:
        result[current_hash] = "\n".join(current_lines)

    return result


def _parse_full_messages(output: str) -> dict[str, str]:
    """Parse git log full message output, keyed by commit hash."""
    result: dict[str, str] = {}
    current_hash: str | None = None
    current_lines: list[str] = []

    for line in output.splitlines():
        if line.startswith("COMMITMSG:"):
            if current_hash and current_lines:
                # Remove trailing ENDMSG and blank lines
                msg = "\n".join(current_lines).strip()
                if msg.endswith("ENDMSG"):
                    msg = msg[:-6].strip()
                result[current_hash] = msg
            current_hash = line[10:].strip()
            current_lines = []
        elif line.strip() == "ENDMSG":
            if current_hash:
                msg = "\n".join(current_lines).strip()
                result[current_hash] = msg
                current_hash = None
                current_lines = []
        elif current_hash is not None:
            current_lines.append(line)

    if current_hash and current_lines:
        msg = "\n".join(current_lines).strip()
        result[current_hash] = msg

    return result


def _assign_merge_sessions(
    commits: list[CommitRecord], repo_root: Path
) -> None:
    """Assign merge session branch names to commits using git ancestry.

    For each 'merge session: <branch>' commit, uses git to find which commits
    are on the branch side of the merge. This correctly handles interleaved
    and parallel sessions.
    """
    commit_map = {c.hash: c for c in commits}

    # Find all merge session commits
    merge_sessions: list[tuple[str, str]] = []  # (hash, session_name)
    for c in commits:
        m = re.match(r"^merge session:\s*(.+)$", c.subject, re.IGNORECASE)
        if m:
            merge_sessions.append((c.hash, m.group(1).strip()))
            c.merge_session = m.group(1).strip()

    # For each merge commit, find branch-side commits via git ancestry
    for merge_hash, session_name in merge_sessions:
        try:
            # Get commits reachable from merge but not from its first parent
            # This gives us exactly the commits that were on the feature branch
            output = run_git(
                repo_root,
                ["log", "--format=%h", f"{merge_hash}^1..{merge_hash}"],
            )
            branch_hashes = set(output.strip().splitlines())
        except subprocess.CalledProcessError:
            # Fallback: if the merge has no parents (shouldn't happen), skip
            continue

        for h in branch_hashes:
            if h in commit_map and h != merge_hash:
                commit_map[h].merge_session = session_name


# ── Category assignment ──────────────────────────────────────────


def load_categories_config(repo_root: Path) -> dict[str, list[str]] | None:
    """Load .claude/changelog-categories.yml. Returns None if not found.

    Also checks the legacy name .claude/changes-categories.yml for
    backwards compatibility.
    """
    config_path = repo_root / ".claude" / "changelog-categories.yml"
    if not config_path.exists():
        # Fallback to legacy name
        config_path = repo_root / ".claude" / "changes-categories.yml"
    if not config_path.exists():
        return None

    # Simple YAML parser for the flat structure we use
    categories: dict[str, list[str]] = {}
    current_key: str | None = None

    for line in config_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            current_key = stripped[:-1]
            categories[current_key] = []
        elif current_key and stripped.startswith("- "):
            categories[current_key].append(stripped[2:].strip())

    return categories if categories else None


def _heuristic_category(filepath: str) -> str:
    """Infer category from file path when YAML config doesn't match."""
    if filepath.startswith(("migrations/", "alembic/")):
        return "Database"
    if filepath.startswith(("deploy/", ".github/")) or filepath.startswith(
        ("Dockerfile", "docker-compose")
    ):
        return "Infrastructure"
    if filepath.startswith("docs/"):
        return "Documentation"
    if filepath.startswith("scripts/"):
        return "Scripts"
    if filepath.startswith("tests/"):
        return "Testing"
    return "Other"


def _categorize_file(
    filepath: str, config: dict[str, list[str]] | None
) -> str | None:
    """Categorize a single file path. Returns category name or None for heuristic."""
    if config:
        for cat_name, prefixes in config.items():
            for prefix in prefixes:
                if "*" in prefix:
                    pattern = prefix.replace("*", "")
                    if filepath.startswith(pattern):
                        return cat_name
                elif filepath.startswith(prefix):
                    return cat_name
    return None


def _primary_category_for_files(
    files: list[FileChange], config: dict[str, list[str]] | None
) -> str:
    """Determine the primary category for a set of files.

    Ignores docs/tests/spec/plan files for category determination,
    falling back to heuristics if nothing matches.
    """
    cat_lines: dict[str, int] = {}

    for f in files:
        if f.is_excluded:
            continue
        # Skip docs and test files for primary category determination
        if f.is_doc:
            continue

        cat = _categorize_file(f.path, config)
        if cat is None:
            cat = _heuristic_category(f.path)
        # Only config-matched categories determine the primary category.
        # Skip heuristic catchalls (Documentation, Testing, Scripts, Other)
        # which can be skewed by auto-generated or boilerplate files.
        if cat in ("Documentation", "Testing", "Scripts", "Other"):
            continue
        cat_lines[cat] = cat_lines.get(cat, 0) + f.added + f.removed

    if cat_lines:
        return max(cat_lines, key=lambda k: cat_lines[k])

    # Fallback: try all files including docs/tests
    for f in files:
        if f.is_excluded:
            continue
        cat = _categorize_file(f.path, config)
        if cat is None:
            cat = _heuristic_category(f.path)
        cat_lines[cat] = cat_lines.get(cat, 0) + f.added + f.removed

    return max(cat_lines, key=lambda k: cat_lines[k]) if cat_lines else "Other"


def categorize_commits(
    commits: list[CommitRecord],
    config: dict[str, list[str]] | None,
) -> list[CategoryGroup]:
    """Group commits by merge session (all commits in a session stay together).

    For commits in a merge session: all commits are grouped under the session's
    primary category (determined by the majority of non-doc code files across
    all commits in the session).

    For commits not in any merge session: individually categorized by their files.
    """
    # Step 1: Group commits by merge session
    session_commits: dict[str, list[CommitRecord]] = {}
    loose_commits: list[CommitRecord] = []

    for commit in commits:
        if commit.merge_session:
            session_commits.setdefault(commit.merge_session, []).append(commit)
        else:
            loose_commits.append(commit)

    groups: list[CategoryGroup] = []

    # Step 2: For each merge session, determine primary category from all files
    for session_name, session_coms in session_commits.items():
        all_files = [f for c in session_coms for f in c.files]
        primary_cat = _primary_category_for_files(all_files, config)
        nice_name = session_name.replace("-", " ").title()
        sub_group = f"{primary_cat} — {nice_name}"

        for c in session_coms:
            c.categories = [primary_cat]

        groups.append(
            CategoryGroup(
                category=primary_cat,
                sub_group=sub_group,
                commits=session_coms,
            )
        )

    # Step 3: For loose commits, group by individual file category
    loose_by_cat: dict[str, list[CommitRecord]] = {}
    for commit in loose_commits:
        cat = _primary_category_for_files(commit.files, config)
        commit.categories = [cat]
        loose_by_cat.setdefault(cat, []).append(commit)

    for cat, coms in loose_by_cat.items():
        groups.append(
            CategoryGroup(
                category=cat,
                sub_group=cat,
                commits=coms,
            )
        )

    # Sort: by category name, then by earliest commit timestamp
    groups.sort(
        key=lambda g: (g.category, g.commits[0].timestamp if g.commits else datetime.min),
    )

    return groups


def determine_primary_category(groups: list[CategoryGroup]) -> str:
    """Find the category with the most total lines changed."""
    cat_totals: dict[str, int] = {}
    for g in groups:
        total = g.total_added + g.total_removed
        cat_totals[g.category] = cat_totals.get(g.category, 0) + total
    if not cat_totals:
        return "changes"
    return max(cat_totals, key=lambda k: cat_totals[k])


# ── Session data ─────────────────────────────────────────────────


def load_sessions(repo_root: Path, target_date: date) -> list[SessionRecord]:
    """Load session state.json files for the given date."""
    yyyymmdd = target_date.strftime("%Y%m%d")
    sessions_dir = repo_root / ".code-sessions"
    sessions: list[SessionRecord] = []

    if not sessions_dir.exists():
        return sessions

    for state_file in sorted(sessions_dir.glob(f"{yyyymmdd}-*/state.json")):
        try:
            data = json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        # Skip sessions without an end timestamp
        if not data.get("end_of_session_timestamp"):
            continue

        sessions.append(
            SessionRecord(
                id=data.get("id", ""),
                name=data.get("name"),
                branch=data.get("branch"),
                start=parse_ts(data.get("start_of_session_timestamp")),
                impl_start=parse_ts(data.get("start_of_implementation_timestamp")),
                end=parse_ts(data.get("end_of_session_timestamp")),
                phase=data.get("phase", "done"),
            )
        )

    # Sort by start timestamp
    sessions.sort(key=lambda s: s.start or datetime.min)
    return sessions


def merge_intervals(
    intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """Sort and merge overlapping time intervals."""
    if not intervals:
        return []
    sorted_ivs = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_ivs[0]]
    for start, end in sorted_ivs[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def compute_time_metrics(
    sessions: list[SessionRecord],
    commits: list[CommitRecord],
) -> TimeMetrics:
    """Compute daily span, total work time, and active time."""

    # Commit-based fallback
    commit_times = [c.timestamp for c in commits]
    commit_span_start = min(commit_times).strftime("%H:%M") if commit_times else None
    commit_span_end = max(commit_times).strftime("%H:%M") if commit_times else None
    commit_span = (
        (max(commit_times) - min(commit_times)) if len(commit_times) >= 2 else None
    )

    if not sessions:
        return TimeMetrics(
            daily_span=None,
            daily_span_start=None,
            daily_span_end=None,
            total_work=None,
            active_time=None,
            commit_span_start=commit_span_start,
            commit_span_end=commit_span_end,
            commit_span=commit_span,
        )

    # Daily span: earliest start → latest end
    starts = [s.start for s in sessions if s.start]
    ends = [s.end for s in sessions if s.end]
    if starts and ends:
        earliest = min(starts)
        latest = max(ends)
        daily_span = latest - earliest
        daily_span_start = earliest.strftime("%H:%M")
        daily_span_end = latest.strftime("%H:%M")
    else:
        daily_span = None
        daily_span_start = None
        daily_span_end = None

    # Total work: sum of individual session durations
    total_work_seconds = 0.0
    for s in sessions:
        if s.start and s.end:
            total_work_seconds += (s.end - s.start).total_seconds()
    total_work = timedelta(seconds=total_work_seconds) if total_work_seconds > 0 else None

    # Active time: merge intervals, sum
    intervals = [
        (s.start, s.end) for s in sessions if s.start and s.end
    ]
    merged = merge_intervals(intervals)
    active_seconds = sum((e - s).total_seconds() for s, e in merged)
    active_time = timedelta(seconds=active_seconds) if active_seconds > 0 else None

    return TimeMetrics(
        daily_span=daily_span,
        daily_span_start=daily_span_start,
        daily_span_end=daily_span_end,
        total_work=total_work,
        active_time=active_time,
        commit_span_start=commit_span_start,
        commit_span_end=commit_span_end,
        commit_span=commit_span,
    )


# ── Report link detection ────────────────────────────────────────


def find_report_link(repo_root: Path, session: SessionRecord) -> str:
    """Check if an implementation report exists for the session."""
    if not session.name:
        return "—"
    yyyymmdd = session.id.split("-")[0] if "-" in session.id else ""
    if not yyyymmdd:
        return "—"
    report_path = (
        repo_root
        / "docs"
        / "implementation"
        / f"{yyyymmdd}-{session.name}"
        / f"{yyyymmdd}-{session.name}-impl-report.md"
    )
    if report_path.exists():
        rel = f"../../implementation/{yyyymmdd}-{session.name}/{yyyymmdd}-{session.name}-impl-report.md"
        return f"[report]({rel})"
    return "—"


# ── Merge session extraction ────────────────────────────────────


def extract_merge_branches(commits: list[CommitRecord]) -> list[str]:
    """Extract unique branch names from 'merge session: <branch>' commits."""
    branches: list[str] = []
    seen: set[str] = set()
    for c in commits:
        m = re.match(r"^merge session:\s*(.+)$", c.subject, re.IGNORECASE)
        if m:
            branch = m.group(1).strip()
            if branch not in seen:
                branches.append(branch)
                seen.add(branch)
    return branches


# ── Language detection ───────────────────────────────────────────


def detect_language(changes_dir: Path) -> str:
    """Detect language from the most recent existing change document."""
    # Look for existing documents
    docs = sorted(changes_dir.glob("*/*-changes-*.md"), reverse=True)
    if not docs:
        return "en"

    # Read first 20 lines and check for Portuguese indicators
    try:
        text = docs[0].read_text()[:2000].lower()
        pt_indicators = [
            "alterações", "sessões", "mudanças", "commits diretos",
            "rascunho", "código", "documentação",
        ]
        if any(indicator in text for indicator in pt_indicators):
            return "pt"
    except OSError:
        pass
    return "en"


# ── SVG generation ───────────────────────────────────────────────
# Merged from generate_session_timeline.py

SVG_WIDTH = 900
LABEL_AREA_WIDTH = 220
TIMELINE_AREA_WIDTH = 640
ROW_HEIGHT = 28
ROW_GAP = 6
BAR_RADIUS = 4
TOP_MARGIN = 50
BOTTOM_MARGIN = 50
ARROW_WIDTH = 8

COLOR_PLANNING = "#60A5FA"
COLOR_IMPLEMENTATION = "#34D399"
COLOR_CANCELLED = "#F87171"
COLOR_GRID = "#E5E7EB"
COLOR_TEXT = "#374151"
COLOR_TEXT_LIGHT = "#6B7280"
COLOR_BG = "#FFFFFF"


def _svg_x_pos(
    dt: datetime, range_start: datetime, range_end: datetime
) -> float:
    """Convert a datetime to an X position in the timeline area."""
    total_span = (range_end - range_start).total_seconds()
    if total_span <= 0:
        return LABEL_AREA_WIDTH
    offset = (dt - range_start).total_seconds()
    fraction = max(0.0, min(1.0, offset / total_span))
    return LABEL_AREA_WIDTH + fraction * TIMELINE_AREA_WIDTH


def _svg_bar_segment(
    x: float,
    y: float,
    width: float,
    height: float,
    color: str,
    round_left: bool,
    round_right: bool,
    arrow_left: bool,
    arrow_right: bool,
) -> str:
    """Generate SVG path for a bar segment."""
    r = min(BAR_RADIUS, width / 2, height / 2)
    aw = min(ARROW_WIDTH, width / 2)

    if width < 1:
        return (
            f'  <rect x="{x:.1f}" y="{y:.1f}" width="{max(width, 0.5):.1f}" '
            f'height="{height}" fill="{color}"/>'
        )

    mid_y = y + height / 2
    parts: list[str] = []

    # Top-left
    if arrow_left:
        parts.append(f"M {x + aw:.1f} {y:.1f}")
    elif round_left and r > 0:
        parts.append(f"M {x + r:.1f} {y:.1f}")
    else:
        parts.append(f"M {x:.1f} {y:.1f}")

    # Top-right
    if arrow_right:
        parts.append(f"L {x + width - aw:.1f} {y:.1f}")
        parts.append(f"L {x + width:.1f} {mid_y:.1f}")
    elif round_right and r > 0:
        parts.append(f"L {x + width - r:.1f} {y:.1f}")
        parts.append(f"Q {x + width:.1f} {y:.1f} {x + width:.1f} {y + r:.1f}")
        parts.append(f"L {x + width:.1f} {y + height - r:.1f}")
        parts.append(
            f"Q {x + width:.1f} {y + height:.1f} {x + width - r:.1f} {y + height:.1f}"
        )
    else:
        parts.append(f"L {x + width:.1f} {y:.1f}")
        parts.append(f"L {x + width:.1f} {y + height:.1f}")

    # Bottom-right (for arrow_right)
    if arrow_right:
        parts.append(f"L {x + width - aw:.1f} {y + height:.1f}")

    # Bottom-left
    if arrow_left:
        parts.append(f"L {x + aw:.1f} {y + height:.1f}")
        parts.append(f"L {x:.1f} {mid_y:.1f}")
    elif round_left and r > 0:
        parts.append(f"L {x + r:.1f} {y + height:.1f}")
        parts.append(f"Q {x:.1f} {y + height:.1f} {x:.1f} {y + height - r:.1f}")
        parts.append(f"L {x:.1f} {y + r:.1f}")
        parts.append(f"Q {x:.1f} {y:.1f} {x + r:.1f} {y:.1f}")
    else:
        parts.append(f"L {x:.1f} {y + height:.1f}")

    parts.append("Z")
    return f'  <path d="{" ".join(parts)}" fill="{color}"/>'


def generate_svg(sessions: list[SessionRecord], target_date: date) -> str | None:
    """Generate session timeline SVG. Returns SVG string or None."""
    # Filter to sessions with start and end
    valid = [s for s in sessions if s.start and s.end]
    if not valid:
        return None

    date_str = target_date.isoformat()
    day_start = datetime.fromisoformat(f"{date_str}T00:00:00+00:00")
    day_end = datetime.fromisoformat(f"{date_str}T23:59:59+00:00")

    # Compute time range
    all_starts = [s.start for s in valid if s.start]
    all_ends = [s.end for s in valid if s.end]
    earliest = min(all_starts)
    latest = max(all_ends)
    range_start = max(earliest, day_start)
    range_end = min(latest, day_end)
    range_start = max(day_start, range_start - timedelta(minutes=15))
    range_end = min(day_end, range_end + timedelta(minutes=15))

    num = len(valid)
    chart_height = num * (ROW_HEIGHT + ROW_GAP)
    svg_height = TOP_MARGIN + chart_height + BOTTOM_MARGIN

    lines: list[str] = []

    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG_WIDTH} {svg_height}" '
        f'width="{SVG_WIDTH}" height="{svg_height}">'
    )
    lines.append(
        f'  <rect width="{SVG_WIDTH}" height="{svg_height}" fill="{COLOR_BG}" rx="8"/>'
    )

    # Styles
    lines.append("  <style>")
    lines.append(
        '    text { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }'
    )
    lines.append(f"    .title {{ font-size: 14px; font-weight: 600; fill: {COLOR_TEXT}; }}")
    lines.append(f"    .label {{ font-size: 11px; fill: {COLOR_TEXT}; }}")
    lines.append(f"    .label-dim {{ font-size: 11px; fill: {COLOR_TEXT_LIGHT}; }}")
    lines.append(
        f"    .tick {{ font-size: 10px; fill: {COLOR_TEXT_LIGHT}; text-anchor: middle; }}"
    )
    lines.append(f"    .legend-text {{ font-size: 11px; fill: {COLOR_TEXT}; }}")
    lines.append("    .duration { font-size: 9px; fill: white; font-weight: 500; }")
    lines.append("  </style>")

    # Title
    lines.append(f'  <text x="16" y="28" class="title">Sessions — {date_str}</text>')

    # Time axis
    total_minutes = (range_end - range_start).total_seconds() / 60.0
    if total_minutes <= 120:
        tick_interval = 15
    elif total_minutes <= 360:
        tick_interval = 30
    elif total_minutes <= 720:
        tick_interval = 60
    else:
        tick_interval = 120

    def time_to_min(dt: datetime) -> float:
        return (dt - day_start).total_seconds() / 60.0

    first_tick = math.ceil(time_to_min(range_start) / tick_interval) * tick_interval
    last_min = time_to_min(range_end)
    tick_y_top = TOP_MARGIN
    tick_y_bottom = TOP_MARGIN + chart_height

    minute = first_tick
    while minute <= last_min:
        tick_dt = day_start + timedelta(minutes=minute)
        tx = _svg_x_pos(tick_dt, range_start, range_end)
        lines.append(
            f'  <line x1="{tx:.1f}" y1="{tick_y_top}" '
            f'x2="{tx:.1f}" y2="{tick_y_bottom}" '
            f'stroke="{COLOR_GRID}" stroke-width="1" stroke-dasharray="4,4"/>'
        )
        hh = int(minute // 60)
        mm = int(minute % 60)
        lines.append(
            f'  <text x="{tx:.1f}" y="{tick_y_bottom + 16}" class="tick">{hh:02d}:{mm:02d}</text>'
        )
        minute += tick_interval

    # Session bars
    for i, session in enumerate(valid):
        row_y = TOP_MARGIN + i * (ROW_HEIGHT + ROW_GAP)
        sess_start = session.start
        sess_impl = session.impl_start
        sess_end = session.end

        label = session.name or session.branch or session.id
        if len(label) > 28:
            label = label[:26] + "…"

        starts_before = sess_start < day_start
        ends_after = sess_end > day_end
        bar_start = max(sess_start, range_start)
        bar_end = min(sess_end, range_end)
        bar_x1 = _svg_x_pos(bar_start, range_start, range_end)
        bar_x2 = _svg_x_pos(bar_end, range_start, range_end)
        bar_width = max(bar_x2 - bar_x1, 2)

        label_class = "label" if session.branch else "label-dim"
        lines.append(
            f'  <text x="{LABEL_AREA_WIDTH - 8}" y="{row_y + ROW_HEIGHT / 2 + 4:.1f}" '
            f'class="{label_class}" text-anchor="end">{escape(label)}</text>'
        )

        min_segment = 3

        # Pick colors: cancelled sessions use red for all segments
        is_cancelled = session.phase == "cancelled"
        color_plan = COLOR_CANCELLED if is_cancelled else COLOR_PLANNING
        color_impl = COLOR_CANCELLED if is_cancelled else COLOR_IMPLEMENTATION

        if sess_impl and sess_impl < sess_end:
            impl_clamped = max(sess_impl, range_start)
            impl_x = _svg_x_pos(impl_clamped, range_start, range_end)
            planning_width = max(impl_x - bar_x1, min_segment)
            impl_width = max(bar_x2 - impl_x, min_segment)
            impl_x = bar_x1 + planning_width

            if planning_width > 0:
                lines.append(
                    _svg_bar_segment(
                        bar_x1, row_y, planning_width, ROW_HEIGHT,
                        color_plan,
                        round_left=not starts_before, round_right=False,
                        arrow_left=starts_before, arrow_right=False,
                    )
                )

            if impl_width > 0:
                lines.append(
                    _svg_bar_segment(
                        impl_x, row_y, impl_width, ROW_HEIGHT,
                        color_impl,
                        round_left=False, round_right=not ends_after,
                        arrow_left=False, arrow_right=ends_after,
                    )
                )

            if planning_width > 40:
                plan_min = (sess_impl - sess_start).total_seconds() / 60.0
                cx = bar_x1 + planning_width / 2
                lines.append(
                    f'  <text x="{cx:.1f}" y="{row_y + ROW_HEIGHT / 2 + 3.5:.1f}" '
                    f'class="duration" text-anchor="middle">{format_duration_m(plan_min)}</text>'
                )

            if impl_width > 40:
                impl_min = (sess_end - sess_impl).total_seconds() / 60.0
                cx = impl_x + impl_width / 2
                lines.append(
                    f'  <text x="{cx:.1f}" y="{row_y + ROW_HEIGHT / 2 + 3.5:.1f}" '
                    f'class="duration" text-anchor="middle">{format_duration_m(impl_min)}</text>'
                )
        else:
            lines.append(
                _svg_bar_segment(
                    bar_x1, row_y, bar_width, ROW_HEIGHT,
                    color_plan,
                    round_left=not starts_before, round_right=not ends_after,
                    arrow_left=starts_before, arrow_right=ends_after,
                )
            )
            if bar_width > 40 and session.total_minutes:
                cx = bar_x1 + bar_width / 2
                lines.append(
                    f'  <text x="{cx:.1f}" y="{row_y + ROW_HEIGHT / 2 + 3.5:.1f}" '
                    f'class="duration" text-anchor="middle">{format_duration_m(session.total_minutes)}</text>'
                )

    # Legend
    legend_y = TOP_MARGIN + chart_height + 36
    lines.append(
        f'  <rect x="{LABEL_AREA_WIDTH}" y="{legend_y - 10}" '
        f'width="14" height="14" rx="3" fill="{COLOR_PLANNING}"/>'
    )
    lines.append(
        f'  <text x="{LABEL_AREA_WIDTH + 20}" y="{legend_y + 1}" '
        f'class="legend-text">Planning</text>'
    )
    lines.append(
        f'  <rect x="{LABEL_AREA_WIDTH + 100}" y="{legend_y - 10}" '
        f'width="14" height="14" rx="3" fill="{COLOR_IMPLEMENTATION}"/>'
    )
    lines.append(
        f'  <text x="{LABEL_AREA_WIDTH + 120}" y="{legend_y + 1}" '
        f'class="legend-text">Implementation</text>'
    )

    # Add "Cancelled" legend entry only if any session is cancelled
    has_cancelled = any(s.phase == "cancelled" for s in sessions)
    if has_cancelled:
        lines.append(
            f'  <rect x="{LABEL_AREA_WIDTH + 230}" y="{legend_y - 10}" '
            f'width="14" height="14" rx="3" fill="{COLOR_CANCELLED}"/>'
        )
        lines.append(
            f'  <text x="{LABEL_AREA_WIDTH + 250}" y="{legend_y + 1}" '
            f'class="legend-text">Cancelled</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


# ── Markdown rendering ───────────────────────────────────────────


def render_document(data: DateData) -> str:
    """Render the complete data document (skeleton + reference appendix)."""
    parts: list[str] = []

    # Header
    draft_suffix = " (DRAFT)" if data.is_draft else ""
    parts.append(f"# Changes — {data.iso_date}{draft_suffix}\n")
    if data.is_draft:
        parts.append(
            "> **DRAFT** — This document covers an incomplete day and may be regenerated.\n"
        )

    # Code/docs summary
    parts.append(_render_stats_summary(data))

    # Metrics line
    parts.append(_render_metrics_line(data))
    parts.append("")

    # Merge sessions
    if data.merge_branches:
        branch_list = ", ".join(f"`{b}`" for b in data.merge_branches)
        parts.append(f"Sessions merged: {branch_list}\n")
    else:
        parts.append("Direct commits to main (no merge sessions).\n")

    parts.append("---\n")

    # Category placeholders
    for group in data.category_groups:
        commit_hashes = ", ".join(c.hash for c in group.commits)
        parts.append(f"<!-- CATEGORY: {group.sub_group} -->")
        parts.append(f"<!-- COMMITS: {commit_hashes} -->")
        parts.append("<!-- PLACEHOLDER -->\n")
        parts.append("---\n")

    # Sessions section
    if data.sessions:
        parts.append(_render_sessions_section(data))
        parts.append("---\n")

    # Commits table
    parts.append(_render_commits_table(data))

    # Reference appendix
    parts.append("")
    parts.append(_render_reference_appendix(data))

    return "\n".join(parts)


def _render_stats_summary(data: DateData) -> str:
    """Render the code/docs summary lines."""
    lines: list[str] = []
    n_commits = len(data.commits)

    if data.code_added > 0 or data.code_removed > 0:
        if n_commits == 1:
            first_time = data.commits[0].time_str
            lines.append(
                f"> **Code changes:** {format_number(data.code_added)} lines added, "
                f"{format_number(data.code_removed)} removed "
                f"in a single commit at `{first_time}`."
            )
        else:
            lines.append(
                f"> **Code changes:** {format_number(data.code_added)} lines added, "
                f"{format_number(data.code_removed)} removed "
                f"across {n_commits} commits."
            )

    if data.doc_added > 0 or data.doc_removed > 0:
        lines.append(
            f"> **Documentation changes:** {format_number(data.doc_added)} lines added, "
            f"{format_number(data.doc_removed)} removed."
        )

    return "\n".join(lines)


def _render_metrics_line(data: DateData) -> str:
    """Render the three time metrics line."""
    m = data.metrics
    parts: list[str] = []

    if m.daily_span and m.daily_span_start and m.daily_span_end:
        parts.append(
            f"**Daily span:** {format_duration_td(m.daily_span)} "
            f"({m.daily_span_start}–{m.daily_span_end})"
        )
    elif m.commit_span and m.commit_span_start and m.commit_span_end:
        parts.append(
            f"**Commit span:** {format_duration_td(m.commit_span)} "
            f"({m.commit_span_start}–{m.commit_span_end})"
        )

    if m.active_time:
        parts.append(f"**Active time:** {format_duration_td(m.active_time)}")
    elif m.daily_span:
        parts.append("**Active time:** —")

    if m.total_work:
        parts.append(f"**Total work:** {format_duration_td(m.total_work)}")
    elif m.daily_span:
        parts.append("**Total work:** —")

    if parts:
        return "> " + " · ".join(parts)
    return ""


def _render_sessions_section(data: DateData) -> str:
    """Render the sessions section with SVG and table."""
    lines: list[str] = []
    lines.append("## Sessions\n")

    if data.svg_path:
        svg_name = data.svg_path.name
        lines.append(f"![Sessions timeline]({svg_name})\n")

    lines.append("| Session | Branch | Time | Report |")
    lines.append("|---------|--------|------|--------|")

    for s in data.sessions:
        session_id = f"`{s.id}`"
        branch = f"`{s.branch}`" if s.branch else "—"
        time_col = s.time_column

        # Report link / status
        if s.phase == "cancelled":
            report = "\u274c CANCELLED"
        elif data.repo_root:
            report = find_report_link(data.repo_root, s)
        else:
            report = "—"

        lines.append(f"| {session_id} | {branch} | {time_col} | {report} |")

    lines.append("")
    return "\n".join(lines)


def _render_commits_table(data: DateData) -> str:
    """Render the commits table."""
    lines: list[str] = []
    lines.append("## Commits\n")
    lines.append("| Time | Lines | Commit | Message |")
    lines.append("|------|-------|--------|---------|")

    for c in data.commits:
        time_str = c.time_str
        added = c.total_added
        removed = c.total_removed
        lines_col = f"+{added}/-{removed}"
        commit_link = f"[`{c.hash}`]({data.github_url}/commit/{c.hash})"
        # Escape pipe characters in message
        msg = c.subject.replace("|", "\\|")
        lines.append(f"| {time_str} | {lines_col} | {commit_link} | {msg} |")

    lines.append("")
    return "\n".join(lines)


def _render_reference_appendix(data: DateData) -> str:
    """Render the reference data appendix for inference."""
    lines: list[str] = []
    lines.append("<!-- REFERENCE DATA — Remove this section from the final document -->\n")

    for group in data.category_groups:
        lines.append(f"## Category: {group.sub_group}\n")

        for c in group.commits:
            lines.append(f"### {c.hash} — {c.subject}\n")
            # Full message if different from subject
            if c.full_message and c.full_message != c.subject:
                lines.append(c.full_message)
                lines.append("")
            # Stat text
            if c.stat_text:
                lines.append("```")
                lines.append(c.stat_text.strip())
                lines.append("```")
                lines.append("")

    return "\n".join(lines)


# ── Catch-up and date range logic ────────────────────────────────


def find_latest_finalized(changes_dir: Path) -> date | None:
    """Find the most recent finalized (non-draft) change document."""
    docs = sorted(changes_dir.glob("*/*-changes-*.md"), reverse=True)
    for doc in docs:
        name = doc.name
        if "-DRAFT" in name:
            continue
        # Extract date from filename: yyyymmdd-changes-...
        m = re.match(r"(\d{8})-changes-", name)
        if m:
            try:
                return datetime.strptime(m.group(1), "%Y%m%d").date()
            except ValueError:
                continue
    return None


def determine_date_range(
    changes_dir: Path,
    mode: str,
    single_date: date | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[date]:
    """Compute the list of dates to process."""
    today = date.today()

    if mode == "single":
        if single_date and single_date > today:
            print(f"Error: Cannot generate changes for a future date ({single_date}).", file=sys.stderr)
            sys.exit(1)
        return [single_date] if single_date else []

    if mode == "range":
        if from_date and to_date:
            if to_date > today:
                to_date = today
            dates = []
            current = from_date
            while current <= to_date:
                dates.append(current)
                current += timedelta(days=1)
            return dates
        return []

    # Catch-up mode
    latest_final = find_latest_finalized(changes_dir)
    if latest_final:
        start = latest_final + timedelta(days=1)
    else:
        start = today - timedelta(days=1)

    dates = []
    current = start
    while current <= today:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def check_existing_document(
    changes_dir: Path, target_date: date, mode: str
) -> str | None:
    """Check for existing documents for this date.

    Returns:
        'skip' — don't process this date
        'delete_draft' — delete the draft and regenerate
        None — no existing doc, proceed normally
    """
    yyyymmdd = target_date.strftime("%Y%m%d")
    yyyy = target_date.strftime("%Y")
    year_dir = changes_dir / yyyy

    if not year_dir.exists():
        return None

    # Check for final docs
    for doc in year_dir.glob(f"{yyyymmdd}-changes-*.md"):
        if "-DRAFT" not in doc.name and "-data" not in doc.name:
            if mode == "catchup":
                return "skip"
            else:
                print(f"  Warning: overwriting finalized document {doc.name}", file=sys.stderr)
                doc.unlink()
                return None

    # Check for drafts
    for doc in year_dir.glob(f"{yyyymmdd}-changes-*-DRAFT.md"):
        doc.unlink()

    # Check for existing data files
    for doc in year_dir.glob(f"{yyyymmdd}-data.md"):
        doc.unlink()

    return None


# ── Main processing ──────────────────────────────────────────────


def to_kebab_case(name: str) -> str:
    """Convert category name to kebab-case for filenames."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def process_date(
    repo_root: Path,
    changes_dir: Path,
    target_date: date,
    github_url: str,
    categories_config: dict[str, list[str]] | None,
    language: str,
    mode: str,
) -> str | None:
    """Process a single date. Returns the data file path or None."""

    # Check existing docs
    status = check_existing_document(changes_dir, target_date, mode)
    if status == "skip":
        return None

    # Collect commits
    commits = collect_commits(repo_root, target_date)
    if not commits:
        return None

    # Load sessions
    sessions = load_sessions(repo_root, target_date)

    # Compute metrics
    metrics = compute_time_metrics(sessions, commits)

    # Categorize
    category_groups = categorize_commits(commits, categories_config)

    # Primary category
    primary_cat = determine_primary_category(category_groups)

    # Merge branches
    merge_branches = extract_merge_branches(commits)

    # Is draft?
    is_draft = target_date == date.today()

    # SVG
    yyyymmdd = target_date.strftime("%Y%m%d")
    yyyy = target_date.strftime("%Y")
    year_dir = changes_dir / yyyy
    year_dir.mkdir(parents=True, exist_ok=True)

    svg_path = None
    svg_content = generate_svg(sessions, target_date)
    if svg_content:
        svg_path = year_dir / f"{yyyymmdd}-sessions.svg"
        svg_path.write_text(svg_content)

    # Build data object
    data = DateData(
        target_date=target_date,
        is_draft=is_draft,
        commits=commits,
        sessions=sessions,
        metrics=metrics,
        category_groups=category_groups,
        merge_branches=merge_branches,
        svg_path=svg_path,
        github_url=github_url,
        repo_root=repo_root,
        language=language,
        primary_category=primary_cat,
    )

    # Render document
    doc_content = render_document(data)

    # Write data file
    data_path = year_dir / f"{yyyymmdd}-data.md"
    data_path.write_text(doc_content)

    return str(data_path.relative_to(repo_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect daily change data for the /daily-changes skill"
    )
    parser.add_argument(
        "date",
        nargs="?",
        help="Single date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        help="Start date for range mode (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        help="End date for range mode (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--repo-root",
        help="Repository root (default: auto-detect via git)",
    )
    return parser.parse_args()


def find_repo_root(hint: str | None = None) -> Path:
    if hint:
        return Path(hint)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        sys.exit("Error: not inside a git repository. Use --repo-root.")


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(args.repo_root)
    changes_dir = repo_root / "docs" / "changes"
    changes_dir.mkdir(parents=True, exist_ok=True)

    github_url = derive_github_url(repo_root)
    categories_config = load_categories_config(repo_root)
    language = detect_language(changes_dir)

    # Determine mode and date range
    if args.from_date and args.to_date:
        mode = "range"
        from_d = date.fromisoformat(args.from_date)
        to_d = date.fromisoformat(args.to_date)
        dates = determine_date_range(changes_dir, mode, from_date=from_d, to_date=to_d)
    elif args.date:
        mode = "single"
        single_d = date.fromisoformat(args.date)
        dates = determine_date_range(changes_dir, mode, single_date=single_d)
    else:
        mode = "catchup"
        dates = determine_date_range(changes_dir, mode)

    if not dates:
        print(json.dumps({"files": [], "skipped": []}))
        return

    generated: list[str] = []
    skipped: list[str] = []

    for d in dates:
        result = process_date(
            repo_root, changes_dir, d, github_url,
            categories_config, language, mode,
        )
        if result:
            generated.append(result)
            print(f"  Generated: {result}", file=sys.stderr)
        else:
            skipped.append(d.isoformat())
            # Only print skip message if there were no commits (not if finalized)
            status = check_existing_document(changes_dir, d, mode)
            if status != "skip":
                print(f"  No commits for {d.isoformat()}, skipping.", file=sys.stderr)
            else:
                print(f"  Skipped {d.isoformat()} (finalized document exists).", file=sys.stderr)

    # Output JSON summary to stdout
    print(json.dumps({"files": generated, "skipped": skipped}))


if __name__ == "__main__":
    main()
