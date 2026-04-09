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

- Collect the list of files touched by this branch's commits:

  ```bash
  BRANCH_FILES=$(git log main..<BRANCH> --name-only --format="" | sort -u)
  ```

- For each file in `git status --porcelain`:
  - If the file is in `$BRANCH_FILES` or under the session's `docs/implementation/` directory: stage and commit it.
  - Otherwise: **stop and ask the user**:
    > "These files have uncommitted changes but were not part of any commit on this branch:
    > `<list>`
    > Should I commit them, discard them, or leave them?"
- Do NOT silently discard, ignore, or commit unfamiliar files.
- **GATE: Do NOT proceed to step 2 until `git status --porcelain` is empty.**

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

### 3. Generate implementation report

Run the wrapup script to record timestamps, compute time breakdown, generate the report, set phase to "done", and copy state.json to docs:

```bash
python3 ~/.claude/skills/session-mgmt-skill/scripts/session_wrapup.py \
  --session-dir "$REPO_ROOT/.code-sessions/current" \
  --repo-root "$REPO_ROOT"
```

Read the JSON output. It contains: `report_path`, `state_copy_path`, `docs_dir`, timing breakdown (`planning_time`, `implementation_time`, `total_time`), `commit_count`, `branch`, `github_url`.

**GATE:** Verify the script exited with code 0. If it failed, show the error and stop.

### 4. Commit report and state.json

```bash
git add docs/implementation/
git commit -m "docs: add implementation report for <session-name>"
```

Use the project's commit authorship conventions if defined in CLAUDE.md.

### 5. Process backlog item (if applicable)

Read `backlog_item_id` from `state.json`. If it is not null, this session was started from a backlog item.

**Archive the backlog item:**

```bash
python3 ~/.claude/skills/session-mgmt-skill/scripts/backlog_ops.py archive \
  "$BACKLOG_ITEM_ID" --docs-dir "<docs_dir from wrapup output>" \
  --repo-root "$REPO_ROOT"
```

**Resolve dependencies:**

```bash
python3 ~/.claude/skills/session-mgmt-skill/scripts/backlog_ops.py resolve-dependency \
  "$BACKLOG_ITEM_ID" --repo-root "$REPO_ROOT"
```

Read the JSON output — it lists `affected_items` with an `unblocked` flag for each.

**Process follow-up items (if the user mentioned any):**

Parse follow-up items from the user's end-session message. Each distinct follow-up becomes a separate backlog item. Examples:

- "end session, follow up with retry backoff and monitoring dashboard" → 2 items
- "end session, we still need to handle edge cases" → 1 item

If the user's phrasing is too vague to extract distinct items, ask:
> "You mentioned follow-ups. Can you list them so I can add them to the backlog?"

For each follow-up, create a backlog item using the logic from `backlog.md` — `/backlog add` with:

- `title`: extracted from the user's phrasing (concise, descriptive)
- `description`: brief context from the completed session
- `importance`: `medium` (default; ask the user if they want to adjust)
- `source.type`: `"follow-up"`
- `source.follow_up_from`: `$BACKLOG_ITEM_ID`
- `source.session_id`: the current session ID
- `source.context`: brief description of what was completed and why follow-up is needed

After creating follow-ups, update the archived parent's `follow_up_items` array with the new IDs.

**Resolve dependencies:**

Scan all remaining items in `$BACKLOG_DIR/*/item.json`. For each item that has `$BACKLOG_ITEM_ID` in its `dependencies` array:

1. Move the ID from `dependencies` to `resolved_dependencies`.

2. If follow-up items were created:
   - Ask the user: "Item `<title>` was blocked by the item we just completed. We also created follow-up items. Should `<title>` be unblocked now, or should the new follow-up items be added as dependencies?"
   - If the user says add follow-ups as dependencies: add the follow-up IDs to the item's `dependencies` array.
   - If the user says unblock: leave `dependencies` as-is (the resolved one was already moved out).

3. If no follow-up items were created and the item's `dependencies` array is now empty: flag it as "unblocked" in the end-session summary.

Update `updated_at` on all modified items.

### 6. Switch to main and merge

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

### 7. Remove worktree and delete branch

```bash
git worktree remove --force <WORKTREE_PATH>
git branch -d <BRANCH>
```

### 8. Prune old sessions

```bash
python3 ~/.claude/skills/session-mgmt-skill/scripts/session_prune.py --repo-root "$MAIN_WORKSPACE"
```

The script removes session folders older than 6 months and outputs JSON with the list of pruned sessions.

### 9. Print summary table

| Item | Status |
|------|--------|
| **Session** | `<id>` (`.code-sessions/<id>`) |
| **Branch merged** | `<branch>` |
| **Planning time** | Xh Ym |
| **Implementation time** | Xh Ym |
| **Total session time** | Xh Ym |
| **Worktree removed** | `<path>` |
| **Impl report** | `<path-to-impl-report.md>` |
| **Backlog item** | `<item-id>` archived to `<docs-path>` / No backlog item |
| **Follow-ups created** | N new backlog items / None |
| **Items unblocked** | `<list of unblocked item titles>` / None |
| **Sessions pruned** | N old sessions removed / None |
| **Current state** | Back on `main` in `<main-workspace>` |

### 10. Quick-check daily changes

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
