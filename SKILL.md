---
name: session-mgmt
description: >-
  Structured development session workflow with braindump, planning, and
  implementation phases using git worktrees. Use when the user says
  "start a session", "new session", "end session", "cancel session",
  "implement the plan", "daily changes", "generate changelog",
  "convert to PDF", "generate my changelog", "quick check",
  "refresh changelog-categories.yml", "setup session management",
  "backlog", "add to backlog", "show backlog", or any similar phrasing.
  Manages the full lifecycle:
  /start-session → braindump → planning → /implement → code → /end-session.
  Also manages a persistent project backlog for tracking planned work across sessions.
metadata:
  author: melo
  version: "1.0.0"
---

# Session Management

A structured workflow for development sessions: braindump freely, plan collaboratively, implement with TDD, merge cleanly.

## The workflow

```
start session → braindump → plan → implement → end session
                                 ↘              ↗
                            cancel session (abort at any point)
```

Every feature, fix, or non-trivial task follows this lifecycle. Sessions are tracked in `.code-sessions/<yyyymmdd>-<hex>/state.json` at the repo root (gitignored). Each session gets its own git branch and worktree for isolation.

## Dispatch

When this skill is triggered, determine which command the user wants and **read the corresponding file**. Follow its instructions exactly.

### Starting a session

**Trigger:** User says "start a session", "new session", "use a session", or similar.

**Action:** Read `./commands/start-session.md` and follow its instructions.

**CRITICAL:** Invoke immediately. No exploration, no investigation, no questions first. The session's braindump and planning phases are where all that work happens.

### Implementing

**Trigger:** Plan is accepted (user approves via ExitPlanMode), or user says "implement", "start implementing", "implement the plan".

**Action:** Read `./commands/implement.md` and follow its instructions.

This creates a branch and worktree, commits the spec and plan, and begins red/green TDD implementation.

### Ending a session

**Trigger:** User says "end session", "wrap up", "merge and push", or similar.

**Action:** Read `./commands/end-session.md` and follow its instructions.

Optional argument: if the user says "end session and deploy" or similar, pass `deploy` as the argument.

### Cancelling a session

**Trigger:** User says "cancel session", "abort session", "discard", or similar.

**Action:** Read `./commands/cancel-session.md` and follow its instructions.

### Daily changes

**Trigger:** User says "daily changes", "generate changelog", "generate my changelog", "what changed today", "quick check", or similar.

**Action:** Read `./commands/daily-changes.md` and follow its instructions.

Arguments are passed through: a date, a date range (`--from ... --to ...`), `--quick-check`, or empty for catch-up mode.

### PDF conversion

**Trigger:** User says "convert to PDF", "generate PDF", "pdf", or provides a markdown file and asks for PDF output.

**Action:** Read `./commands/pdf.md` and follow its instructions.

Arguments: the path to the markdown file (and optionally the output path).

### Refresh changelog categories

**Trigger:** User says "refresh changelog-categories.yml", "generate changelog categories", "infer categories", or similar.

**Action:** Read `./commands/refresh-changelog-categories.md` and follow its instructions.

### Backlog

**Trigger:** User says "backlog", "add to backlog", "show backlog", "what's in the backlog?", or any mention of "backlog" in the context of project work (e.g., "we can improve X later, add to backlog", "move the webhook item above auth in the backlog").

**Action:** Read `./commands/backlog.md` and follow its instructions.

Supports subcommands: `/backlog`, `/backlog add`, `/backlog show <id>`, `/backlog edit <id>`, `/backlog rank`, `/backlog link <id> <id>`, `/backlog remove <id>`, `/backlog filter`.

Natural language containing "backlog" routes through the same command logic.

### Setup

**Trigger:** User says "setup session management", "install session dependencies", "setup PDF dependencies", or similar.

**Action:** Read `./commands/setup.md` and follow its instructions.

## Shared concepts

### Session state

Each session is tracked in `$REPO_ROOT/.code-sessions/<yyyymmdd>-<hex>/state.json`:

```json
{
  "id": "20260223-abc123",
  "name": "feature-name",
  "phase": "braindump|planning|implementing|done|cancelled",
  "prompts": [
    {"timestamp": "2026-02-23T12:01:00Z", "content": "user message text..."}
  ],
  "start_of_session_timestamp": "2026-02-23T12:00:00Z",
  "start_of_implementation_timestamp": "2026-02-23T12:30:00Z",
  "end_of_session_timestamp": "2026-02-23T14:00:00Z",
  "branch": "feature-name",
  "worktree_path": ".worktrees/feature-name",
  "backlog_item_id": null
}
```

The `backlog_item_id` field is set when a session is started from a backlog item. Used by end-session (to archive the item) and cancel-session (to revert it to open).

The `.code-sessions/` directory is gitignored and dockerignored. Session folders are kept as historical records and auto-pruned after 6 months.

In a worktree, `.code-sessions/current` is a symlink to the active session folder so skills can find the state without knowing the random ID.

### Backlog

A persistent stack-ranked list of work items stored in `$REPO_ROOT/.code-sessions/backlog/`. Each item lives in its own folder (`backlog/<id>/item.json` + attachments). An `index.json` holds the ordered list of IDs — position is priority.

Items have status `open`, `in-progress`, `archived`, or `cancelled`. Only `open` and `in-progress` items appear in the index. Items carry an `importance` label (`critical`/`high`/`medium`/`low`) independent of rank position.

**Audit trail:** All objects maintain bidirectional links. Sessions reference backlog items via `backlog_item_id` in `state.json`. Backlog items reference sessions via `active_session`. Follow-ups link to parents via `source.follow_up_from` and parents track follow-ups via `follow_up_items`. Dependencies move from `dependencies` to `resolved_dependencies` when completed — never deleted.

### Worktrees

- Live in `$REPO_ROOT/.worktrees/<branch>` (project-local, gitignored)
- Symlink `.env`, `.legacy_env`, and `data/` from the main workspace
- Get their own dependency installation (`.venv`, `node_modules`, etc.)
- Share the same database, cache, and infrastructure
- List active worktrees: `git worktree list`

### Plan files

Every session produces committed documentation in `docs/implementation/<yyyymmdd>-<session-name>/`:

- **Spec** (`-spec.md`): the *what* — requirements, API design, data model, behavior, constraints
- **Plan** (`-plan.md`): the *how* — implementation steps, layers, migrations, tests
- **Impl Report** (`-impl-report.md`): generated by end-session — timing, commits with links

### Time awareness

Claude does not know the current time. All timestamps MUST be captured via bash commands:
```bash
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

### Project conventions

Each project's CLAUDE.md may define additional conventions for:
- Commit authorship and message format
- Doc file location overrides
- Testing requirements
- Deployment procedures

Always defer to the project's CLAUDE.md when it conflicts with defaults here.
