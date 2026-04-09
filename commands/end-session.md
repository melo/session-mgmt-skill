Wrap up the current session: generate an implementation report, merge back to main, and clean up.

No arguments required.

## Detect context

1. Determine current branch and working directory:
   ```bash
   CURRENT_BRANCH=$(git branch --show-current)
   REPO_ROOT=$(git rev-parse --show-toplevel)
   ```

2. If the current branch is **not** `main` (i.e., in a session worktree), go to **Session Wrap-Up**.
   If the current branch **is** `main`, go to **Main Workspace Wrap-Up**.

---

## Session Wrap-Up

### 1. Pre-flight checks

**GATE — The session MUST NOT end with a dirty worktree or failing tests.**

**1a. Ensure all changes are committed:**

Run `git status --porcelain`. If non-empty:

- Review each uncommitted file. Stage and commit with a proper message if the intent is clear.
- If unsure about any files, **ask the user** before proceeding. Do NOT silently discard or ignore files.
- **Do NOT proceed to step 2 until `git status --porcelain` is empty.**

**1b. Ensure tests pass:**

Run the project's test suite (look at CLAUDE.md or standard conventions for the test command).

- **If tests fail:** STOP. Fix the failing tests, commit the fix, and re-run. If you cannot fix them, ask the user for guidance. Do NOT proceed until tests pass.
- **If no test suite exists:** Skip this check.

### 2. Find the session

Read the session state from the worktree:
```bash
STATE_FILE="$REPO_ROOT/.code-sessions/current/state.json"
```

If the file doesn't exist, warn the user: "No session state found at .code-sessions/current/state.json. Proceeding without session tracking." Continue with the merge anyway — just skip the session-specific steps (timestamps, report).

### 3. Record end timestamp

Capture the current UTC time via bash (Claude does not know the current time — you MUST use a command):
```bash
END_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

Set `end_of_session_timestamp` to `$END_TS` in `state.json`.

### 4. Compute time breakdown

From `state.json`, compute:

- **Planning time:** `start_of_session_timestamp` → `start_of_implementation_timestamp`
- **Implementation time:** `start_of_implementation_timestamp` → `end_of_session_timestamp`
- **Total session time:** `start_of_session_timestamp` → `end_of_session_timestamp`

Format each as `Xh Ym`. If a timestamp is null, show "N/A" for that phase.

### 5. Generate implementation report

Before leaving the worktree, create the report file.

**Determine the docs path** from `state.json` — use the same `docs/implementation/<yyyymmdd>-<session-name>/` directory where the spec and plan live.

**Collect commit list:**
```bash
git log main..<BRANCH> --format="%H %s"
```

**Derive GitHub URL** from the remote:
```bash
REMOTE_URL=$(git remote get-url origin 2>/dev/null)
```
Parse it to get `https://github.com/<owner>/<repo>`. Handle both SSH (`git@github.com:owner/repo.git`) and HTTPS (`https://github.com/owner/repo.git`) formats. Strip `.git` suffix.

**Write the report** to `<yyyymmdd>-<session-name>-impl-report.md`:

```markdown
# Implementation Report — <session-name>

| Item | Value |
|------|-------|
| **Session ID** | `<id>` |
| **Session folder** | `.code-sessions/<id>` |
| **Branch** | `<branch>` |
| **Worktree** | `<worktree-path>` |
| **Planning time** | Xh Ym |
| **Implementation time** | Xh Ym |
| **Total session time** | Xh Ym |
| **Commits** | N |

## Commits

| Hash | Message |
|------|---------|
| [`abcdef1`](https://github.com/owner/repo/commit/abcdef1...) | First line of commit message |
| [`abcdef2`](https://github.com/owner/repo/commit/abcdef2...) | First line of commit message |
| ... | ... |
```

### 6. Copy state.json to docs

Copy the session's `state.json` into the same `docs/implementation/<yyyymmdd>-<session-name>/` directory so it is committed alongside the spec, plan, and report:
```bash
cp "$REPO_ROOT/.code-sessions/current/state.json" "<docs-path>/state.json"
```

### 7. Commit report and state.json

```bash
git add docs/implementation/
git commit -m "docs: add implementation report for <session-name>"
```
Use the project's commit authorship conventions if defined in CLAUDE.md.

### 8. Update session state

Set `phase` to `"done"` in `state.json`. Do NOT delete the session folder — it serves as a historical record.

### 9. Switch to main and merge

```bash
MAIN_WORKSPACE=<main-repo-root>  # from state.json or detect via git worktree list
cd "$MAIN_WORKSPACE"
git merge --no-ff <BRANCH> -m "merge session: <BRANCH>"
```

**If merge conflicts occur:**
- Show the conflicting files
- Ask the user with these options:
  1. "Abort merge and keep worktree" — run `git merge --abort`, stop
  2. "Manually resolve conflicts now" — keep merge state, provide instructions, stop
  3. "Abort merge and delete worktree anyway" — run `git merge --abort`, continue cleanup
- If options 1 or 2 chosen, **stop** — do not remove worktree or branch

### 10. Remove worktree and delete branch

```bash
git worktree remove --force <WORKTREE_PATH>
git branch -d <BRANCH>
```

### 11. Prune old sessions

Scan `.code-sessions/` for folders where the `yyyymmdd` prefix in the folder name is older than 6 months. Delete those folders:
```bash
SIX_MONTHS_AGO=$(date -u -d '6 months ago' +%Y%m%d)
for dir in "$MAIN_WORKSPACE"/.code-sessions/*/; do
  FOLDER_DATE=$(basename "$dir" | cut -c1-8)
  if [ "$FOLDER_DATE" -lt "$SIX_MONTHS_AGO" ] 2>/dev/null; then
    rm -rf "$dir"
    echo "Pruned old session: $(basename "$dir")"
  fi
done
```

### 12. Print summary table

| Item | Status |
|------|--------|
| **Session** | `<id>` (`.code-sessions/<id>`) |
| **Branch merged** | `<branch>` |
| **Planning time** | Xh Ym |
| **Implementation time** | Xh Ym |
| **Total session time** | Xh Ym |
| **Worktree removed** | `<path>` |
| **Impl report** | `<path-to-impl-report.md>` |
| **Sessions pruned** | N old sessions removed / None |
| **Current state** | Back on `main` in `<main-workspace>` |

### 13. Quick-check daily changes

After printing the summary table, run the daily-changes command with `--quick-check`. This checks how many days are behind on daily changelog documents and offers to generate them.

Read `./commands/daily-changes.md` and follow its quick-check instructions.

---

## Main Workspace Wrap-Up

Use this path when already on `main` with no active session worktree.

1. **Commit any pending changes:**
   Run `git status --porcelain`. Stage and commit intentional changes. Delete temp/generated files. Ask the user about anything uncertain.

2. **Print summary table:**

   | Item | Status |
   |------|--------|
   | **Committed** | `<description or "nothing to commit">` |
   | **Cleaned up** | `<removed files, or "nothing to clean">` |
   | **Current state** | Clean `main` in `<workspace>` |
