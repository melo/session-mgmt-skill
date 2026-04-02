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
Read each and pick the one with `phase` of `"braindump"` or `"planning"` and the most recent `start_of_session_timestamp`.

If no active session found, tell the user: "No active session found. Use /start-session first." and **stop**.

### 2. Determine the session name

By now you know what the session is about from the planning conversation. Pick a descriptive kebab-case name (e.g., `add-user-search`, `fix-auth-bug`, `redesign-session-skills`).

If `$ARGUMENTS` is provided, use that as the name instead.

Update `state.json`: set `name` to the chosen name.

### 3. Record implementation start

Capture the current UTC time via bash (Claude does not know the current time — you MUST use a command):
```bash
IMPL_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```
Set `start_of_implementation_timestamp` to `$IMPL_TS` in `state.json`.

### 4. Ensure unique branch name

```bash
git branch --list <name>
```
If the branch exists, try `<name>-2`, `<name>-3`, etc. until unique.

### 5. Ensure `.worktrees/` is gitignored

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
git check-ignore -q "$REPO_ROOT/.worktrees" 2>/dev/null || echo '.worktrees/' >> "$REPO_ROOT/.gitignore"
```

### 6. Create the worktree

```bash
mkdir -p "$REPO_ROOT/.worktrees"
WORKTREE_PATH="$REPO_ROOT/.worktrees/<BRANCH>"
git worktree add "$WORKTREE_PATH" -b <BRANCH>
```

### 6a. Check VSCode worktree exclusion

Check if `.devcontainer/devcontainer.json` exists and whether it already excludes `.worktrees/` from the file watcher (look for `files.watcherExclude` containing `.worktrees`). If not, recommend to the user:

> "Consider adding `.worktrees/` to `files.watcherExclude` and `files.exclude` in your devcontainer.json to prevent VSCode from indexing worktree contents."

### 7. Symlink gitignored files

From the main repo root into the worktree. Skip any that don't exist:
```bash
for f in .env .legacy_env data; do
  [ -e "$REPO_ROOT/$f" ] && ln -sf "$REPO_ROOT/$f" "$WORKTREE_PATH/$f"
done
```

### 8. Symlink session folder into worktree

```bash
mkdir -p "$WORKTREE_PATH/.code-sessions"
ln -sf "$REPO_ROOT/.code-sessions/<SESSION_ID>" "$WORKTREE_PATH/.code-sessions/current"
```
This lets all skills running in the worktree find the session via `.code-sessions/current/` without knowing the random ID.

### 9. Install dependencies

Detect the project's dependency manager and install:
- If `uv.lock` exists: `cd "$WORKTREE_PATH" && uv sync`
- If `package-lock.json` exists: `cd "$WORKTREE_PATH" && npm ci`
- If `yarn.lock` exists: `cd "$WORKTREE_PATH" && yarn install --frozen-lockfile`
- Otherwise: skip

### 10. Update session state

Update `state.json`:
- `branch`: the branch name
- `worktree_path`: the full worktree path
- `phase`: `"implementing"`

### 11. Write spec and plan files

Determine the docs directory. Default convention:
```
docs/implementation/<yyyymmdd>-<session-name>/
```
where `<yyyymmdd>` is from `start_of_session_timestamp` in state.json.

The project can override this convention via its CLAUDE.md instructions.

Create the directory and write:
- `<yyyymmdd>-<session-name>-spec.md` — the *what*: requirements, API design, data model, behavior, constraints. Synthesized from the planning conversation.
- `<yyyymmdd>-<session-name>-plan.md` — the *how*: implementation steps, layers, migrations, tests.

### 12. Commit spec and plan

```bash
cd "$WORKTREE_PATH"
git add docs/implementation/
git commit -m "docs: add spec and plan for <session-name>"
```
Use the project's commit authorship conventions if defined in CLAUDE.md.

### 13. Begin implementation

Work through the plan step by step in the worktree. All file paths are relative to the worktree root.

**Rules:**
- **Red/green TDD:** Write tests first. See them fail. Then write the implementation to make them pass. This is mandatory.
- **Commit often.** After each significant, self-contained change (new module, completed layer, passing tests). Each commit should leave the codebase in a coherent state.
- **All other rules** come from the project's CLAUDE.md and project-level skills.
- Use **TodoWrite** to track progress through plan items.

### 14. Print a summary before starting work

- Session ID: `<SESSION_ID>`
- Session name: `<name>`
- Worktree: `$REPO_ROOT/.worktrees/<branch>`
- Branch: `<branch>`
- Spec: `<spec-file-path>`
- Plan: `<plan-file-path>`
