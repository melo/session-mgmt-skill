# session-mgmt

**An agent skill for structured development sessions with braindump, planning, and implementation phases using git worktrees.**

Dump your ideas freely, plan collaboratively, implement with TDD, merge cleanly. Every session produces committed documentation (spec, plan, implementation report) and an isolated git worktree so parallel sessions never interfere.

```
> start a session
> let's start planning
> [plan is accepted]
> end session
```

## Stability

The author has been using this skill extensively over the past few months. Although we are always improving it, it is stable to use. Bug reports and contributions are welcome.

## What about Superpowers?

When writing this skill, the author did not know about Claude Code's [Superpowers](https://docs.anthropic.com/en/docs/claude-code/superpowers) feature, only discovering it in version 5. We will continue developing and using our version to explore the design space, but Superpowers has a larger user base and tighter integration with Claude Code. If you are evaluating workflow tools, consider Superpowers alongside this skill — they solve similar problems with different approaches.

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

<svg viewBox="0 0 720 140" xmlns="http://www.w3.org/2000/svg" style="max-width:720px;width:100%">
  <defs>
    <marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <path d="M0,0 L8,3 L0,6" fill="#666"/>
    </marker>
  </defs>
  <!-- Phase boxes -->
  <rect x="10" y="30" width="110" height="40" rx="6" fill="#e8f0fe" stroke="#4285f4" stroke-width="1.5"/>
  <text x="65" y="55" text-anchor="middle" font-family="system-ui,sans-serif" font-size="13" fill="#1a73e8">start session</text>
  <rect x="155" y="30" width="100" height="40" rx="6" fill="#e8f0fe" stroke="#4285f4" stroke-width="1.5"/>
  <text x="205" y="55" text-anchor="middle" font-family="system-ui,sans-serif" font-size="13" fill="#1a73e8">braindump</text>
  <rect x="290" y="30" width="80" height="40" rx="6" fill="#e8f0fe" stroke="#4285f4" stroke-width="1.5"/>
  <text x="330" y="55" text-anchor="middle" font-family="system-ui,sans-serif" font-size="13" fill="#1a73e8">plan</text>
  <rect x="405" y="30" width="110" height="40" rx="6" fill="#e8f4e5" stroke="#34a853" stroke-width="1.5"/>
  <text x="460" y="55" text-anchor="middle" font-family="system-ui,sans-serif" font-size="13" fill="#1e8e3e">implement</text>
  <rect x="550" y="30" width="110" height="40" rx="6" fill="#e8f0fe" stroke="#4285f4" stroke-width="1.5"/>
  <text x="605" y="55" text-anchor="middle" font-family="system-ui,sans-serif" font-size="13" fill="#1a73e8">end session</text>
  <!-- Arrows between phases -->
  <line x1="120" y1="50" x2="153" y2="50" stroke="#666" stroke-width="1.5" marker-end="url(#arrow)"/>
  <line x1="255" y1="50" x2="288" y2="50" stroke="#666" stroke-width="1.5" marker-end="url(#arrow)"/>
  <line x1="370" y1="50" x2="403" y2="50" stroke="#666" stroke-width="1.5" marker-end="url(#arrow)"/>
  <line x1="515" y1="50" x2="548" y2="50" stroke="#666" stroke-width="1.5" marker-end="url(#arrow)"/>
  <!-- Cancel box -->
  <rect x="290" y="95" width="140" height="35" rx="6" fill="#fce8e6" stroke="#ea4335" stroke-width="1.5" stroke-dasharray="5,3"/>
  <text x="360" y="117" text-anchor="middle" font-family="system-ui,sans-serif" font-size="12" fill="#c5221f">cancel session</text>
  <!-- Dashed lines from cancel -->
  <line x1="370" y1="70" x2="370" y2="93" stroke="#ea4335" stroke-width="1.2" stroke-dasharray="4,3"/>
  <line x1="460" y1="70" x2="430" y2="93" stroke="#ea4335" stroke-width="1.2" stroke-dasharray="4,3"/>
</svg>

#### 1. Start a session

Say "start a session" or similar. This:

- Creates a session folder (`.code-sessions/<id>/`) with a `state.json` file
- Enters **plan mode**
- Puts the agent in **braindump phase** — it will listen without interrupting

You can also start a session from a backlog item: "start a session on the webhook retry item".

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

- Generates an **implementation report** with timing and commit links
- Copies the session's `state.json` into the docs folder (committed alongside spec, plan, and report)
- Merges the branch back to `main`
- Reports time breakdown (planning vs implementation)
- Cleans up the worktree
- Archives the backlog item (if the session was started from one)
- Offers to create follow-up backlog items

#### Cancelling a session

At any point, say "cancel session" to abort without merging. This removes the worktree and branch (if they exist), marks the session as cancelled, and returns to main. If the session was started from a backlog item, the item is reverted to open.

### Backlog

The skill includes a persistent backlog for tracking planned work across sessions. Items are stack-ranked (position = priority) and stored in `.code-sessions/backlog/`. Each item has an importance label (critical/high/medium/low) independent of rank.

Key operations:

- **Add items** during or outside sessions — context is captured automatically
- **Rank items** by moving them relative to each other
- **Link items** with dependencies ("A blocks B") or references ("A relates to B")
- **Start sessions from backlog items** — the item's context pre-seeds the braindump
- **Archive completed items** — moved to the session's docs folder at end-session
- **Follow-up items** — created at end-session, linked to the archived parent

### Other commands

| Command | What it does |
| ------- | ------------ |
| "backlog" / "add to backlog" / "show backlog" | Manage a persistent, stack-ranked backlog of work items. Supports add, show, edit, rank, link, remove, and filter subcommands. |
| "daily changes" / "generate my changelog" / "quick check" | Generate "changes to check" documents from git history. Catches up from the last document through today. Today's changes are marked as DRAFT. Quick-check mode reports how many days are behind without generating documents. |
| "convert to PDF" / "pdf `<file>`" | Convert a Markdown file to a styled PDF with page breaks and page numbers. |
| "refresh changelog-categories.yml" | Analyze the project structure and generate or refresh the `.claude/changelog-categories.yml` config file. |
| "setup session management" | Install all Python and system dependencies required by the skill. |

### Project-specific configuration

#### Category config for daily changes

Create `.claude/changelog-categories.yml` at your repo root to map file paths to category names. You can generate one automatically by saying **"refresh changelog-categories.yml"** — the agent will analyze your project structure and produce a sensible default.

Or write one manually:

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

#### Worktree configuration

Worktrees live in `$REPO_ROOT/.claude/worktrees/<branch>` (Claude Code's default location). To copy gitignored files (like `.env` or `data/`) into new worktrees, create a `.worktreeinclude` file at your repo root:

```text
.env
.env.local
data/
```

Each line follows `.gitignore` syntax. Files listed here are copied from the main workspace into every new worktree.

#### Project conventions

Each project's CLAUDE.md can define conventions that override defaults:

- Commit authorship and message format
- Documentation file location
- Testing requirements
- Deployment procedures

## How it works

```text
SKILL.md (dispatch + shared concepts)
    ↓
commands/                            ← agent reads the matching command file
├── start-session.md                 (create session, braindump phase)
├── implement.md                     (branch, worktree, spec+plan commit, TDD)
├── end-session.md                   (report, merge, cleanup)
├── cancel-session.md                (abort, cleanup)
├── backlog.md                       (persistent work item tracking)
├── daily-changes.md                 (changelog generation)
├── pdf.md                           (markdown → PDF conversion)
├── refresh-changelog-categories.md  (infer category config from project)
└── setup.md                         (install dependencies)
    ↓
scripts/                             ← executed by command files
├── session_init.py                  (session folder creation, backlog linking)
├── worktree_setup.py                (branch, worktree, file copying, deps detection)
├── session_wrapup.py                (timestamps, report generation)
├── backlog_ops.py                   (all backlog CRUD operations)
├── session_prune.py                 (prune sessions older than 6 months)
├── refresh_categories.py            (scan project, write changelog-categories.yml)
├── collect_daily_changes.py         (git data collection, session parsing, SVG timelines)
└── md2pdf.py                        (markdown → HTML → PDF via WeasyPrint)
```

The SKILL.md entry point dispatches to the right command file based on what the user says. Each command file contains complete, self-contained instructions. Scripts handle mechanical work (data collection, PDF rendering, file operations) so the agent focuses on narrative and decision-making.

### Session state

Each session is tracked in `.code-sessions/<yyyymmdd>-<hex>/state.json` at the repo root (gitignored). It stores:

- Session ID and name
- Current phase
- Timestamps for session start, implementation start, and session end
- Branch name and worktree path
- Backlog item reference (if started from one)

State transitions follow this sequence:

```text
braindump → planning → implementing → done
                                    ↘ cancelled (from any phase)
```

Each transition is recorded in `state.json` with timestamps. The `done` and `cancelled` states are terminal — a session cannot be resumed once ended or cancelled.

Session folders are kept as historical records and auto-pruned after 6 months.

### Worktrees

- Live in `$REPO_ROOT/.claude/worktrees/<branch>` (Claude Code's default location, gitignored)
- Copy gitignored files listed in `.worktreeinclude` from the main workspace
- Get their own dependency installation (`.venv`, `node_modules`, etc.)
- Share the same database, cache, and infrastructure
- List active worktrees: `git worktree list`

### The audit trail

Every completed session produces four committed files in `docs/implementation/<date>-<name>/`:

1. **Spec** (`-spec.md`): What was built and why
2. **Plan** (`-plan.md`): How it was built
3. **Implementation report** (`-impl-report.md`): What actually happened — timing, commits, branch
4. **Session state** (`state.json`): Raw session metadata with timestamps

## Design rationale

### Separating thinking from doing

The braindump → plan → implement sequence is deliberate. When you braindump freely, you explore the problem space without the pressure of making decisions. When planning starts, the agent helps you organize and challenge those ideas. By the time implementation begins, the "what" and "how" are settled — no wasted effort building the wrong thing.

This separation also helps the agent. With a clear spec and plan, it produces better code because it understands the full context rather than discovering requirements mid-implementation.

### Why worktrees

Git worktrees give each session its own working directory and branch, without needing to stash or commit half-finished work. Benefits:

- **Parallel sessions.** Multiple agent instances can work on different features simultaneously — each in its own worktree with its own branch.
- **Clean isolation.** No risk of one session's changes interfering with another's. Each worktree has its own dependency installation.
- **No stash juggling.** You never lose work switching between tasks.
- **Shared infrastructure.** All worktrees share the same database, cache, and environment files via `.worktreeinclude`.

### Why session state files

The `.code-sessions/<id>/state.json` file tracks timestamps, branch name, and phase. This enables:

- **Time awareness.** You can see how long planning took vs implementation. Over time, this reveals patterns.
- **Implementation reports.** At the end of each session, a report is generated and committed alongside the spec and plan. This creates an audit trail.
- **Historical record.** Session folders are kept (pruned after 6 months) so you can review past sessions.
- **Centralized state.** Scratch files and session metadata all live in one place.

### Why red/green TDD

The implement command mandates writing tests first. This isn't dogma — it's practical:

- **Spec-driven.** The spec and plan define behavior. Tests encode that behavior. Implementation satisfies the tests.
- **Catches regressions early.** When the agent writes tests first, it validates its understanding of the requirements before writing implementation code.
- **Confidence to refactor.** With tests already passing, you can restructure code knowing that behavior is preserved.

### Why the draft system in daily-changes

1. **Catch-up after gaps.** After a weekend or vacation, running daily changes with no arguments generates documents for all missing days automatically.
2. **Work-in-progress days.** Today's changes are marked as DRAFT because the day isn't over. Running the command again regenerates the draft with any new commits.

### Advantages at a glance

| Benefit | How |
| ------- | --- |
| No wasted implementation effort | Spec and plan agreed before coding starts |
| Parallel development | Worktrees isolate sessions |
| Time tracking | Automatic timestamps for each phase |
| Audit trail | Spec + plan + report committed per feature |
| Persistent backlog | Stack-ranked work items survive across sessions |
| Catch-up friendly | Daily changes auto-generate for missing days |
| Project-agnostic | Skill works in any git repository |
| Customizable | Category config, path conventions overridable via CLAUDE.md |

## License

MIT
