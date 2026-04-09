Cancel the current session without merging. Discards the branch and worktree (if any), records the cancellation, and returns to main.

No arguments required.

## Steps

### 1. Detect context

```bash
CURRENT_BRANCH=$(git branch --show-current)
REPO_ROOT=$(git rev-parse --show-toplevel)
```

### 2. Find the active session

**If the current branch is NOT `main`** (i.e., in a worktree):

Read the session state from the worktree:
```bash
STATE_FILE="$REPO_ROOT/.code-sessions/current/state.json"
```
If the file doesn't exist, warn the user: "No session state found at .code-sessions/current/state.json." Then try the scan approach below.

**If the current branch IS `main`**, or the symlink above didn't exist:

Scan for the most recent active session:
```bash
ls -1d "$REPO_ROOT"/.code-sessions/*/state.json 2>/dev/null | sort -r
```
Read each `state.json` and collect those where `phase` is NOT `"done"` and NOT `"cancelled"`. Sort by `start_of_session_timestamp` (most recent first).

- **If exactly one active session is found**, use it.
- **If multiple active sessions are found**, list them and ask the user which one to cancel.
- **If no active session is found**, print: "No active session found. Nothing to cancel." and **STOP**.

Save the original phase value as `ORIGINAL_PHASE` for the summary table.

### 3. Record end timestamp

Capture the current UTC time (Claude does not know the current time — you MUST use a command):
```bash
END_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```
Set `end_of_session_timestamp` to `$END_TS` in `state.json`.

### 4. Worktree and branch cleanup (conditional)

Read `branch` and `worktree_path` from `state.json`.

**Case A: Worktree and branch exist** (phase was `implementing`):

1. Check for uncommitted changes:
   ```bash
   git -C "$WORKTREE_PATH" status --porcelain
   ```
   If there are uncommitted changes, warn the user:
   > "Warning: There are uncommitted changes in the worktree that will be lost:"
   > (show the list)
   > "Continue with cancellation?"

   If the user says no, **STOP** without cancelling.

2. Determine the main workspace path:
   ```bash
   MAIN_WORKSPACE=$(git worktree list --porcelain | awk '/^worktree / && !/'"$WORKTREE_PATH"'/{print $2; exit}')
   ```
   Or more reliably, parse `git worktree list` for the entry on branch `main`.

3. Switch to the main workspace:
   ```bash
   cd "$MAIN_WORKSPACE"
   ```

4. Remove the worktree:
   ```bash
   git worktree remove --force "$WORKTREE_PATH"
   ```

5. Delete the branch (force-delete since it was never merged):
   ```bash
   git branch -D "$BRANCH"
   ```

**Case B: No worktree/branch** (phase was `braindump` or `planning`):

Nothing to clean up. Proceed to step 5.

### 5. Update session state

Set `phase` to `"cancelled"` in `state.json`. Do NOT delete the session folder — it serves as a historical record.

### 5b. Revert backlog item (if applicable)

Read `backlog_item_id` from `state.json`. If it is not null, this session was started from a backlog item.

Revert the item to its previous state:
```bash
BACKLOG_ITEM_ID=$(jq -r '.backlog_item_id' "$STATE_FILE")
BACKLOG_DIR="$REPO_ROOT/.code-sessions/backlog"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq --arg ts "$TS" \
  '.status = "open" | .active_session = null | .updated_at = $ts' \
  "$BACKLOG_DIR/$BACKLOG_ITEM_ID/item.json" > /tmp/item_tmp.json \
  && mv /tmp/item_tmp.json "$BACKLOG_DIR/$BACKLOG_ITEM_ID/item.json"
```

The item stays in its original rank position in `index.json`. No dependency changes.

### 6. Prune old sessions

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

Use `$MAIN_WORKSPACE` if it was set (Case A), otherwise use `$REPO_ROOT`.

### 7. Print summary table

This MUST be the last thing output:

| Item | Status |
|------|--------|
| **Session** | `<id>` (`.code-sessions/<id>`) |
| **Phase when cancelled** | `<ORIGINAL_PHASE>` |
| **Branch deleted** | `<branch>` / No branch created |
| **Worktree removed** | `<path>` / No worktree created |
| **Backlog item** | `<item-id>` reverted to open / No backlog item |
| **Sessions pruned** | N old sessions removed / None |
| **Current state** | Back on `main` in `<workspace-path>` |
