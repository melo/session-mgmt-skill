# Plan: Session-Mgmt-Skill Review, Performance, and Documentation

## Context

The session-mgmt-skill has been heavily updated recently (backlog command, end-session improvements, quick-check). This session does a full pass across three areas: consistency/correctness, performance (packaging deterministic sequences into Python scripts), and README documentation updates.

---

## Phase 1: Command File Review — Consistency, Gates, Ambiguity

Fix issues in command markdown files. Each item is a targeted edit.

### 1.1 end-session: fix phase ordering bug
**File:** `commands/end-session.md`
- Move "set phase to done" BEFORE copying state.json to docs and committing. Currently phase is set AFTER commit, so the committed state.json shows "implementing" instead of "done".
- Sequence: record end timestamp → set phase="done" → copy state.json to docs → commit.

### 1.2 end-session: replace ambiguous "recognize a change" with deterministic check
**File:** `commands/end-session.md`
- Replace "if you don't recognize a change" with: check `git log main..<BRANCH> --name-only` for expected files. Anything not in that list → ask the user.
- Add gate: `git status --porcelain` must be empty before proceeding.

### 1.3 end-session: define follow-up creation syntax
**File:** `commands/end-session.md`
- Add parsing guidance: how to extract follow-up items from natural language, what fields to set, when to ask for clarification.

### 1.4 start-session: disambiguate multiple backlog matches
**File:** `commands/start-session.md`
- If multiple backlog items match a title search, list them and ask user to pick. If none match, say so and continue without backlog item.

### 1.5 start-session: enumerate common test commands
**File:** `commands/start-session.md`
- Add ordered fallback list: CLAUDE.md → Makefile → package.json → pyproject.toml → Cargo.toml → go.mod → ask user.

### 1.6 implement: handle multiple active sessions on context recovery
**File:** `commands/implement.md`
- When the LLM loses context (conversation crash/restart) and needs to recover the active session, implement.md step 1 scans `.code-sessions/` for state.json files with phase "braindump" or "planning". If a previous session was started days ago but never finished, AND the user started a new one today, there would be two non-terminal sessions. Currently the command silently picks the most recent.
- Fix: if multiple non-terminal sessions found, list them (ID, name, start timestamp, phase) and ask the user which one to implement.

### 1.7 cancel-session: add options for uncommitted changes
**File:** `commands/cancel-session.md`
- Present options: cancel anyway, commit first, stash to main, abort cancellation.

### 1.8 daily-changes: add tone/style guidance and explicit DRAFT logic
**File:** `commands/daily-changes.md`
- Add tone guidance (technical, concise, specific).
- Clarify DRAFT = today's date; re-run replaces existing DRAFT; finalized docs are not overwritten by default, but can be regenerated if the user explicitly asks (e.g., "rewrite all changelogs" after skill improvements).

### 1.9 backlog add: add atomicity verification
**File:** `commands/backlog.md`
- After appending to index.json, verify the item appears. If not, retry or clean up orphaned folder.

### 1.10 Worktree location: adopt Claude Code best practices
**Files:** `commands/implement.md`, `SKILL.md`, `README.md`
- Change worktree location from `$REPO_ROOT/.worktrees/<branch>` to `$REPO_ROOT/.claude/worktrees/<branch>` (Claude Code's default).
- Replace custom symlink logic (`.env`, `.legacy_env`, `data/`) with `.worktreeinclude` file approach: document that users should create a `.worktreeinclude` in their repo root listing gitignored files to copy.
- Update `.gitignore` entries accordingly (`.claude/worktrees/`).

### 1.11 Fix macOS date incompatibility in prune logic
**Files:** `commands/end-session.md`, `commands/cancel-session.md`
- Replace `date -d '6 months ago'` (GNU-only) with Python one-liner or defer to `session_prune.py` (Phase 2).

---

## Phase 2: Python Scripts — Package Deterministic Sequences

Create scripts in `scripts/` that bundle multi-step bash/jq sequences. Each script: argparse, JSON to stdout, progress/errors to stderr, stdlib only, atomic file writes (`.tmp` in same dir then `os.rename`).

### 2.1 `session_init.py` — replaces start-session steps 1, 3-8
```
python3 session_init.py [--backlog-item <ID_OR_TITLE>] [--repo-root <PATH>]
→ JSON: {session_id, session_dir, timestamp, backlog_item, gitignore_updated, errors}
→ Exit 0=ok, 1=fatal, 2=ambiguous backlog (includes ambiguous_matches array)
```
LLM still does: test gate, plan mode, braindump interaction.

### 2.2 `worktree_setup.py` — replaces implement steps 3-10
```
python3 worktree_setup.py --session-id <ID> --branch <NAME> --name <NAME> [--repo-root <PATH>]
→ JSON: {branch, worktree_path, branch_renamed, symlinks/worktreeinclude, dependency_manager, dependency_install_cmd, errors}
→ Uses .claude/worktrees/<branch> location
```
LLM still does: run dep install command, write spec/plan, commit, begin TDD.

### 2.3 `session_wrapup.py` — replaces end-session steps 3-7
```
python3 session_wrapup.py --session-dir <PATH> [--repo-root <PATH>]
→ JSON: {report_path, state_copy_path, docs_dir, timing breakdown, commit_count, github_url, errors}
→ Sets phase="done", records end timestamp, generates report markdown, copies state.json to docs
```
LLM still does: pre-flight checks, git commit, backlog processing, merge, cleanup.

### 2.4 `backlog_ops.py` — replaces all backlog bash/jq operations
```
python3 backlog_ops.py <subcommand> [options] [--repo-root <PATH>]
Subcommands: init, add, list, show, edit, rank, link, remove, archive, update-status, resolve-dependency, filter
→ JSON output per subcommand
→ Exit 2 for "needs user confirmation" (e.g., remove with dependents)
```
LLM still does: natural language interpretation, user confirmation prompts.

### 2.5 `session_prune.py` — replaces prune logic in end-session and cancel-session
```
python3 session_prune.py [--repo-root <PATH>] [--dry-run]
→ JSON: {pruned: [...], count: N}
→ Portable (no GNU date dependency)
```

### 2.6 `refresh_categories.py` — replaces refresh-changelog-categories steps 1-4
```
python3 refresh_categories.py [--repo-root <PATH>] [--dry-run]
→ JSON: {categories, preserved_from_existing, config_path, written}
→ Manual YAML writing (no PyYAML dependency)
```

After each script: update the corresponding command `.md` to call the script and interpret JSON output.

---

## Phase 3: README Updates

All changes to `README.md`.

### 3.1 Remove alpha label, add stability paragraph
- Delete the `> **ALPHA SOFTWARE.**` blockquote.
- Add a "## Stability" section before "## Why": "The author has been using this skill extensively over the past few months. Although we are always improving it, it is stable to use."

### 3.2 Add "What about Superpowers?" section
- After Stability, before Why.
- Explain: didn't know about Superpowers when writing this, discovered it at version 5, keeping our version to explore the design space, but Superpowers has a larger user base — consider both.

### 3.3 Add backlog to commands table and add Backlog subsection
- New row in Other commands table.
- New ### Backlog subsection describing the feature.

### 3.4 Document state sequence in detail
- In "### Session state" section, add transition diagram and explanation of terminal states.

### 3.5 Document quick-check mode
- Update daily-changes row in commands table to mention quick-check.

### 3.6 Update "How it works" tree
- Add `backlog.md` to commands tree.
- Add all new Python scripts to scripts tree.

### 3.7 Fix worktree path documentation
- Change to `.claude/worktrees/<branch>` (covered by 1.10).
- Document `.worktreeinclude` approach.

### 3.8 Convert workflow diagram to inline SVG
- Replace the ASCII `start session → braindump → plan → implement → end session` diagram with an inline SVG.
- Keep the architecture file tree as a code block (SVG adds complexity without benefit for trees).

---

## Implementation Order

1. Phase 1 (command fixes) — all independent, do sequentially
2. Phase 2 (scripts) — order: 2.5 → 2.4 → 2.1 → 2.2 → 2.3 → 2.6, update command files after each
3. Phase 3 (README) — can start after Phase 1, finalize tree after Phase 2

## Verification

- Read each modified command file end-to-end to check coherence
- Run each new Python script with `--help` and a basic invocation to verify it works
- Review final README for accuracy against implementation
