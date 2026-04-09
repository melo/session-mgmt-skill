Start implementing the plan from the current session.

Optional argument: `$ARGUMENTS` — a branch name override. If not provided, Claude picks a descriptive kebab-case name based on the session context.

## Steps

### 1. Find the active session

Use the session ID you remembered from `/start-session`. The session folder is at:
```
$REPO_ROOT/.code-sessions/<SESSION_ID>/state.json
```

If you cannot find the session ID (e.g., context was lost), scan for the most recent active session:
```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
# Find state.json files where phase is "braindump" or "planning"
ls -1d "$REPO_ROOT"/.code-sessions/*/state.json 2>/dev/null | sort -r | head -5
```
Read each and pick those with `phase` of `"braindump"` or `"planning"`.

**GATE — Disambiguate if needed:**

- If exactly one active session found: use it.
- If multiple found: list them (ID, name, start timestamp, phase) and ask the user which one to implement.
- If none found: tell the user "No active session found. Use /start-session first." and **stop**.

### 2. Determine the session name

By now you know what the session is about from the planning conversation. Pick a descriptive kebab-case name (e.g., `add-user-search`, `fix-auth-bug`, `redesign-session-skills`).

If `$ARGUMENTS` is provided, use that as the name instead.

### 3. Run the worktree setup script

```bash
python3 ~/.claude/skills/session-mgmt-skill/scripts/worktree_setup.py \
  --session-id "<SESSION_ID>" \
  --branch "<name>" \
  --name "<name>" \
  --repo-root "$(git rev-parse --show-toplevel)"
```

The script handles: branch uniqueness (appends `-2`, `-3` if needed), `.claude/worktrees/` gitignore, worktree creation, `.worktreeinclude` file copying, session symlink, dependency detection, and state.json update (name, branch, worktree_path, phase, implementation timestamp).

Read the JSON output:

- `branch`: the actual branch name (may differ from input if renamed)
- `worktree_path`: absolute path to the worktree
- `dependency_install_cmd`: command to install dependencies (or null if none detected)
- `worktreeinclude_copied` / `worktreeinclude_skipped`: which files were copied or skipped

**GATE:** If exit code is non-zero, show the error and stop.

### 4. Install dependencies

If `dependency_install_cmd` from the script output is not null, run it:

```bash
<dependency_install_cmd from JSON output>
```

### 5. Write spec and plan files

Determine the docs directory. Default convention:

```text
docs/implementation/<yyyymmdd>-<session-name>/
```

where `<yyyymmdd>` is from `start_of_session_timestamp` in state.json.

The project can override this convention via its CLAUDE.md instructions.

Create the directory and write:

- `<yyyymmdd>-<session-name>-spec.md` — the *what*: requirements, API design, data model, behavior, constraints. Synthesized from the planning conversation.
- `<yyyymmdd>-<session-name>-plan.md` — the *how*: implementation steps, layers, migrations, tests.

### 6. Commit spec and plan

```bash
cd "$WORKTREE_PATH"
git add docs/implementation/
git commit -m "docs: add spec and plan for <session-name>"
```

Use the project's commit authorship conventions if defined in CLAUDE.md.

### 7. Print a summary before starting work

- Session ID: `<SESSION_ID>`
- Session name: `<name>`
- Worktree: `<worktree_path from script output>`
- Branch: `<branch from script output>`
- Spec: `<spec-file-path>`
- Plan: `<plan-file-path>`

### 8. Begin implementation

Work through the plan step by step in the worktree. All file paths are relative to the worktree root.

**Rules:**

- **Red/green TDD:** Write tests first. See them fail. Then write the implementation to make them pass. This is mandatory.
- **Commit often.** After each significant, self-contained change (new module, completed layer, passing tests). Each commit should leave the codebase in a coherent state.
- **All other rules** come from the project's CLAUDE.md and project-level skills.
- Use **TodoWrite** to track progress through plan items.
