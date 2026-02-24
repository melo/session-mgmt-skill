Wrap up the current session: generate an implementation report, merge back to main, and clean up.

Optional argument: `$ARGUMENTS` — if it contains the word "deploy" (e.g., user says `/end-session deploy` or "end session and deploy"), run the **Deploy to Production** phase after the session wrap-up but before the final summary table.

## Detect context

1. Determine current branch and working directory:
   ```bash
   CURRENT_BRANCH=$(git branch --show-current)
   REPO_ROOT=$(git rev-parse --show-toplevel)
   ```

2. Check if deploy was requested:
   - If `$ARGUMENTS` contains "deploy" (case-insensitive), set `DEPLOY_REQUESTED=true`
   - Otherwise, set `DEPLOY_REQUESTED=false`

3. If the current branch is **not** `main` (i.e., in a session worktree), go to **Session Wrap-Up**.
   If the current branch **is** `main`, go to **Main Workspace Wrap-Up**.

---

## Session Wrap-Up

### 1. Find the session

Read the session state from the worktree:
```bash
STATE_FILE="$REPO_ROOT/.code-sessions/current/state.json"
```
If the file doesn't exist, warn the user: "No session state found at .code-sessions/current/state.json. Proceeding without session tracking." Continue with the merge anyway — just skip the session-specific steps (timestamps, report).

### 2. Record end timestamp

Capture the current UTC time via bash (Claude does not know the current time — you MUST use a command):
```bash
END_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```
Set `end_of_session_timestamp` to `$END_TS` in `state.json`.

### 3. Compute time breakdown

From `state.json`, compute:
- **Planning time:** `start_of_session_timestamp` → `start_of_implementation_timestamp`
- **Implementation time:** `start_of_implementation_timestamp` → `end_of_session_timestamp`
- **Total session time:** `start_of_session_timestamp` → `end_of_session_timestamp`

Format each as `Xh Ym`. If a timestamp is null, show "N/A" for that phase.

### 4. Server cleanup

Check for a port file in the session folder:
```bash
PORT_FILE="$REPO_ROOT/.code-sessions/current/server-port"
```
If the file exists, read the port and try to stop the server:
```bash
PORT=$(cat "$PORT_FILE" | tr -d '[:space:]')
curl -s --max-time 2 "http://localhost:${PORT}/_/kill"
sleep 2
```

**IMPORTANT:** Use `/_/kill` ONLY. Do NOT fall back to PID scans. Orphan servers are safer than accidentally killing a parallel session's server. If `/_/kill` fails or times out, log it:
> "Could not stop server on port $PORT via /_/kill — it may be an orphan. Check manually if needed."

### 5. Commit uncommitted changes

Run `git status --porcelain`. If non-empty:
- Stage relevant files and commit with a proper message
- If unsure about any files, ask the user

### 6. Generate implementation report

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

Commit this file:
```
docs: add implementation report for <session-name>
```

### 7. Switch to main and merge

```bash
MAIN_WORKSPACE=<main-repo-root>  # from state.json or detect via git worktree list
cd "$MAIN_WORKSPACE"
GIT_AUTHOR_NAME="Claude" GIT_AUTHOR_EMAIL="melo-claude@simplicidade.org" \
GIT_COMMITTER_NAME="Claude" GIT_COMMITTER_EMAIL="melo-claude@simplicidade.org" \
git merge --no-ff <BRANCH> -m "merge session: <BRANCH>"
```

**If merge conflicts occur:**
- Show the conflicting files
- Ask the user with these options:
  1. "Abort merge and keep worktree" — run `git merge --abort`, stop
  2. "Manually resolve conflicts now" — keep merge state, provide instructions, stop
  3. "Abort merge and delete worktree anyway" — run `git merge --abort`, continue cleanup
- If options 1 or 2 chosen, **stop** — do not remove worktree or branch

### 8. Remove worktree and delete branch

```bash
git worktree remove --force <WORKTREE_PATH>
git branch -d <BRANCH>
```

### 9. Push main to origin

```bash
cd "$MAIN_WORKSPACE"
git push origin main
```

### 10. Update session state

Set `phase` to `"done"` in `state.json`. Do NOT delete the session folder — it serves as a historical record.

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

### 12. Deploy to production (conditional)

**Skip this entire section if `DEPLOY_REQUESTED` is false.** Go straight to step 13 (Print summary table).

If `DEPLOY_REQUESTED` is true, deploy the just-pushed code to production:

#### 12a. Wait for GitHub Actions CI to build the Docker image

The push to `main` in step 9 triggers the `Docker Build & Publish` workflow. The image must be built and pushed to `ghcr.io` before we can deploy.

```bash
# Get the SHA of the commit we just pushed (the merge commit on main)
DEPLOY_SHA=$(git -C "$MAIN_WORKSPACE" rev-parse HEAD)
SHORT_SHA=$(echo "$DEPLOY_SHA" | cut -c1-7)
```

Poll the workflow run status using `gh`:
```bash
# Find the workflow run triggered by our push
gh run list --workflow=docker-publish.yml --branch=main --limit=5 --json databaseId,headSha,status,conclusion
```

Look for the run whose `headSha` matches `$DEPLOY_SHA`. Then watch it:
```bash
gh run watch <RUN_ID> --exit-status
```

This blocks until the run completes. If it **fails**:
- Print the failure details: `gh run view <RUN_ID> --log-failed`
- Warn the user: "CI build failed — deployment aborted. Fix the build and deploy manually."
- Set `DEPLOY_STATUS="CI build failed"` and skip to the summary table.

If it **succeeds**, continue to 12b.

#### 12b. SSH into production and pull the new image

```bash
ssh -p 2211 maia@lara.sable-toad.ts.net 'cd ~/workspace/deploy/app && docker compose pull'
```

If SSH or pull fails, warn the user and set `DEPLOY_STATUS="Image pull failed"`. Skip to summary.

#### 12c. Restart containers

```bash
ssh -p 2211 maia@lara.sable-toad.ts.net 'cd ~/workspace/deploy/app && docker compose up -d'
```

If this fails, warn the user and set `DEPLOY_STATUS="Container restart failed"`. Skip to summary.

#### 12d. Wait for containers to become healthy

Wait a few seconds for containers to start, then check health:
```bash
# Wait for initial startup
sleep 10

# Check container health status
ssh -p 2211 maia@lara.sable-toad.ts.net 'docker ps --filter "name=maia-" --format "table {{.Names}}\t{{.Status}}"'
```

Poll up to 5 times (every 10 seconds) until all `maia-*` containers report `(healthy)`:
```bash
ssh -p 2211 maia@lara.sable-toad.ts.net 'docker inspect --format="{{.Name}} {{.State.Health.Status}}" maia-api maia-backoffice maia-indexer maia-demo 2>/dev/null'
```

**Success criteria:** All containers that existed before the deploy report `healthy`. The `maia-indexer` container may take longer (120s start period) — wait up to 3 minutes for it.

If all healthy: set `DEPLOY_STATUS="Deployed successfully (SHA: $SHORT_SHA)"`
If timeout (3 min): set `DEPLOY_STATUS="Containers not yet healthy after 3 min — check manually"` and print the current status of each container.

#### 12e. Quick smoke test

If containers are healthy, do a quick HTTP check:
```bash
ssh -p 2211 maia@lara.sable-toad.ts.net 'curl -sf --max-time 5 http://localhost:5000/_/health && echo " API OK" || echo " API FAIL"'
ssh -p 2211 maia@lara.sable-toad.ts.net 'curl -sf --max-time 5 http://localhost:5001/_/health && echo " Backoffice OK" || echo " Backoffice FAIL"'
```

Append the smoke test results to `DEPLOY_STATUS`.

### 13. Print summary table

This MUST be the last thing you output:

| Item | Status |
|------|--------|
| **Session** | `<id>` (`.code-sessions/<id>`) |
| **Branch merged** | `<branch>` |
| **Planning time** | Xh Ym |
| **Implementation time** | Xh Ym |
| **Total session time** | Xh Ym |
| **Server** | Stopped (port N) / Not running / Failed to stop |
| **Worktree removed** | `<path>` |
| **Impl report** | `<path-to-impl-report.md>` |
| **Pushed to origin** | `main` |
| **Sessions pruned** | N old sessions removed / None |
| **Deploy** | `<DEPLOY_STATUS>` / Skipped (not requested) |
| **Current state** | Back on `main` in `<main-workspace>` |

---

## Main Workspace Wrap-Up

Use this path when already on `main` with no active session worktree.

1. **Check for stale worktrees and branches:**
   ```bash
   git worktree list
   git branch --list --no-column
   ```
   If there are worktrees other than the main workspace or branches other than `main`, ask the user whether to merge/delete them or leave them.

2. **Commit any pending changes:**
   Run `git status --porcelain`. Stage and commit intentional changes. Delete temp/generated files. Ask the user about anything uncertain.

3. **Check for session folders with active state:**
   Look for any `.code-sessions/*/state.json` where `phase` is not `"done"`. Warn the user about these orphaned sessions and ask what to do.

4. **Push main to origin:**
   ```bash
   git push origin main
   ```

5. **Deploy to production (conditional):**

   **Skip this step if `DEPLOY_REQUESTED` is false.** Go straight to step 6 (Print summary table).

   If `DEPLOY_REQUESTED` is true, follow the same deploy process as Session Wrap-Up step 12 (12a through 12e). The only difference is that `DEPLOY_SHA` comes from the current HEAD on main rather than a merge commit.

6. **Print summary table:**

   | Item | Status |
   |------|--------|
   | **Committed** | `<description or "nothing to commit">` |
   | **Cleaned up** | `<removed files, or "nothing to clean">` |
   | **Stale branches** | `<merged/deleted, or "none">` |
   | **Orphaned sessions** | `<list or "none">` |
   | **Pushed to origin** | `main` |
   | **Deploy** | `<DEPLOY_STATUS>` / Skipped (not requested) |
   | **Current state** | Clean `main` in `<workspace>` |
