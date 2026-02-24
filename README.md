# session-mgmt

**An agent skill for structured development sessions with braindump, planning, and implementation phases using git worktrees.**

Dump your ideas freely, plan collaboratively, implement with TDD, merge cleanly. Every session produces committed documentation (spec, plan, implementation report) and an isolated git worktree so parallel sessions never interfere.

```
> start a session
> let's start planning
> [plan is accepted]
> end session
```

## Why

Coding agents default to diving straight into implementation. You describe something, they start writing code. This leads to wasted effort when the requirements weren't clear, conflicts when multiple features are in flight, and no audit trail of what was planned vs what was built.

This skill enforces a deliberate sequence: braindump → plan → implement → merge. The braindump phase lets you explore the problem space without pressure. Planning synthesizes your ideas into a spec and implementation plan. By the time code is written, the "what" and "how" are settled.

Git worktrees give each session its own working directory and branch. No stash juggling, no half-finished work blocking other tasks. All worktrees share the same database and infrastructure.

The skill also generates daily changelog documents from git history, so you can catch up on what changed after a weekend or vacation. Today's changes are marked as drafts; previous days are finalized automatically.

## Install

The skill follows the [Agent Skills specification](https://agentskills.io/specification). Clone it into your agent's skills directory:

```bash
# Claude Code
git clone https://github.com/melo/session-mgmt-skill.git ~/.claude/skills/session-mgmt-skill
```

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and working
- Git repository (the skill works in any git repo)
- For PDF conversion: system Python 3 with `weasyprint` and `markdown` packages, plus system libraries (pango, cairo, gdk-pixbuf)

After cloning, say **"setup session management"** and the skill will install all Python and system dependencies automatically. Or install them manually:

```bash
sudo uv pip install --system weasyprint markdown
# Debian/Ubuntu: sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0
# macOS: brew install pango gdk-pixbuf
```

## Usage

The agent loads the skill automatically when you mention sessions, planning, changelogs, or PDF conversion. You can also invoke it directly with `/session-mgmt`.

### The workflow

```
start session → braindump → plan → implement → end session
                                 ↘              ↗
                            cancel session (abort at any point)
```

#### 1. Start a session

Say "start a session" or similar. This:
- Creates a session folder (`.code-sessions/<id>/`) with a `state.json` file
- Enters **plan mode**
- Puts the agent in **braindump phase** — it will listen without interrupting

#### 2. Braindump your ideas

Just talk. Describe what you want to build, paste references, add files. The agent absorbs everything silently — it won't ask questions, suggest alternatives, or explore your codebase. When you're done, say something like:

> "Let's start planning"

The agent then:
- Synthesizes your braindump
- Suggests improvements and alternatives
- Prepares a **spec** (the *what*) and a **plan** (the *how*)
- Iterates with you until both are agreed upon

#### 3. Accept the plan

When you approve the plan, the agent automatically:
- Creates a git branch and worktree for isolated development
- Commits the spec and plan files as the first commit
- Starts coding using red/green TDD

#### 4. End the session

Say "end session". This:
- Generates an **implementation report** (committed alongside spec and plan)
- Merges the branch back to `main`
- Pushes to origin
- Reports time breakdown (planning vs implementation)
- Cleans up the worktree

Optional: say "end session and deploy" to trigger a production deployment after merging.

#### Cancelling a session

At any point, say "cancel session" to abort without merging. This removes the worktree and branch (if they exist), marks the session as cancelled, and returns to main.

### Other commands

| Command | What it does |
|---------|-------------|
| "daily changes" | Generate "changes to check" documents from git history. Catches up from the last document through today. Today's changes are marked as DRAFT. |
| "convert to PDF" / "pdf `<file>`" | Convert a Markdown file to a styled PDF with page breaks and page numbers. |
| "setup session management" | Install all Python and system dependencies required by the skill. |

### Project-specific configuration

#### Category config for daily changes

Create `.claude/changes-categories.yml` at your repo root to map file paths to category names:

```yaml
Frontend:
  - src/components/
  - src/pages/
Backend:
  - src/api/
  - src/services/
Database:
  - migrations/
Infrastructure:
  - deploy/
  - .github/
```

Without this file, the agent infers categories automatically from directory structure.

#### Project conventions

Each project's CLAUDE.md can define conventions that override defaults:
- Commit authorship and message format
- Documentation file location
- Testing requirements
- Deployment procedures

## How it works

```
SKILL.md (dispatch + shared concepts)
    ↓
commands/                 ← agent reads the matching command file
├── start-session.md      (create session, braindump phase)
├── implement.md          (branch, worktree, spec+plan commit, TDD)
├── end-session.md        (report, merge, push, cleanup)
├── cancel-session.md     (abort, cleanup)
├── daily-changes.md      (changelog generation)
├── pdf.md                (markdown → PDF conversion)
└── setup.md              (install dependencies)
    ↓
scripts/                  ← executed by command files
├── collect_daily_changes.py  (git data collection, session parsing, SVG timelines)
└── md2pdf.py                 (markdown → HTML → PDF via WeasyPrint)
```

The SKILL.md entry point dispatches to the right command file based on what the user says. Each command file contains complete, self-contained instructions. Scripts handle mechanical work (data collection, PDF rendering) so the agent focuses on narrative and decision-making.

### Session state

Each session is tracked in `.code-sessions/<yyyymmdd>-<hex>/state.json` at the repo root (gitignored). It stores:
- Session ID and name
- Current phase (`braindump` → `planning` → `implementing` → `done` or `cancelled`)
- Timestamps for session start, implementation start, and session end
- Branch name and worktree path

Session folders are kept as historical records and auto-pruned after 6 months.

### Worktrees

- Live in `/worktrees/<repo-name>-<branch>` (or a similar persistent location)
- Symlink `.env`, `.legacy_env`, and `data/` from the main workspace
- Get their own dependency installation (`.venv`, `node_modules`, etc.)
- Share the same database, cache, and infrastructure
- List active worktrees: `git worktree list`

### The audit trail

Every completed session produces three committed documents in `docs/implementation/<date>-<name>/`:

1. **Spec** (`-spec.md`): What was built and why
2. **Plan** (`-plan.md`): How it was built
3. **Implementation report** (`-impl-report.md`): What actually happened — timing, commits, branch

## Design rationale

### Separating thinking from doing

The braindump → plan → implement sequence is deliberate. When you braindump freely, you explore the problem space without the pressure of making decisions. When planning starts, the agent helps you organize and challenge those ideas. By the time implementation begins, the "what" and "how" are settled — no wasted effort building the wrong thing.

This separation also helps the agent. With a clear spec and plan, it produces better code because it understands the full context rather than discovering requirements mid-implementation.

### Why worktrees

Git worktrees give each session its own working directory and branch, without needing to stash or commit half-finished work. Benefits:

- **Parallel sessions.** Multiple agent instances can work on different features simultaneously — each in its own worktree with its own branch.
- **Clean isolation.** No risk of one session's changes interfering with another's. Each worktree has its own dependency installation.
- **No stash juggling.** You never lose work switching between tasks.
- **Shared infrastructure.** All worktrees share the same database, cache, and environment files via symlinks.

### Why session state files

The `.code-sessions/<id>/state.json` file tracks timestamps, branch name, and phase. This enables:

- **Time awareness.** You can see how long planning took vs implementation. Over time, this reveals patterns.
- **Implementation reports.** At the end of each session, a report is generated and committed alongside the spec and plan. This creates an audit trail.
- **Historical record.** Session folders are kept (pruned after 6 months) so you can review past sessions.
- **Centralized state.** Port files, scratch files, and session metadata all live in one place.

### Why red/green TDD

The implement command mandates writing tests first. This isn't dogma — it's practical:

- **Spec-driven.** The spec and plan define behavior. Tests encode that behavior. Implementation satisfies the tests.
- **Catches regressions early.** When the agent writes tests first, it validates its understanding of the requirements before writing implementation code.
- **Confidence to refactor.** With tests already passing, you can restructure code knowing that behavior is preserved.

### Why no PID scans

When stopping servers, we only use the application's `/_/kill` endpoint — never PID-based process scanning. A PID scan might match and kill a server belonging to a different worktree running in the same container. An orphan server is harmless; a killed parallel session loses work.

### Why the draft system in daily-changes

1. **Catch-up after gaps.** After a weekend or vacation, running daily changes with no arguments generates documents for all missing days automatically.
2. **Work-in-progress days.** Today's changes are marked as DRAFT because the day isn't over. Running the command again regenerates the draft with any new commits.

### Advantages at a glance

| Benefit | How |
|---------|-----|
| No wasted implementation effort | Spec and plan agreed before coding starts |
| Parallel development | Worktrees isolate sessions |
| Time tracking | Automatic timestamps for each phase |
| Audit trail | Spec + plan + report committed per feature |
| Safe parallel servers | No PID scans, session-aware port files |
| Catch-up friendly | Daily changes auto-generate for missing days |
| Project-agnostic | Skill works in any git repository |
| Customizable | Category config, path conventions overridable via CLAUDE.md |

## License

MIT
