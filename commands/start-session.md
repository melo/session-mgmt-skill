## MANDATORY — When to invoke this skill

**If the user says "start a session", "new session", "use a session", or ANY similar phrasing, invoke this skill IMMEDIATELY.** Do NOT run any other tools first — no exploration, no investigation, no questions. The session's braindump and planning phases are where all that work happens.

---

Start a new development session with structured braindump and planning phases.

No arguments required. A random session ID is generated automatically.

## Steps

1. **Determine the repo root:**
   ```bash
   REPO_ROOT=$(git rev-parse --show-toplevel)
   ```

2. **Generate a session ID** in the format `<yyyymmdd>-<6-char-hex>`:
   ```bash
   SESSION_ID="$(date -u +%Y%m%d)-$(openssl rand -hex 3)"
   ```

3. **Create the session folder:**
   ```bash
   mkdir -p "$REPO_ROOT/.code-sessions/$SESSION_ID"
   ```

4. **Ensure `.code-sessions/` is in `.gitignore`:**
   Check if `.code-sessions/` already appears in `$REPO_ROOT/.gitignore`. If not, append it:
   ```bash
   grep -qxF '.code-sessions/' "$REPO_ROOT/.gitignore" 2>/dev/null || echo '.code-sessions/' >> "$REPO_ROOT/.gitignore"
   ```
   Do the same for `.dockerignore` if it exists.

5. **Capture the current UTC timestamp** (Claude does not know the current time — you MUST use a bash command):
   ```bash
   SESSION_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
   ```

6. **Write `state.json`** (use `$SESSION_TS` for the start timestamp):
   ```json
   {
     "id": "<SESSION_ID>",
     "name": null,
     "phase": "braindump",
     "start_of_session_timestamp": "<SESSION_TS>",
     "start_of_implementation_timestamp": null,
     "end_of_session_timestamp": null,
     "branch": null,
     "worktree_path": null
   }
   ```

7. **CRITICAL — Remember the session ID.** You must retain the value of `SESSION_ID` for the entire conversation. Never lose it. You will need it when `/implement` runs later.

8. **Enter plan mode** if not already in plan mode.

9. **Print a short confirmation:**
   > Session `<SESSION_ID>` started. I'm in braindump mode — go ahead and dump your ideas. I'll listen without interrupting. When you're ready to start planning, say "let's start planning".

10. **STOP.** After printing the confirmation, your turn is over. Do NOT launch any agents, do NOT explore the codebase, do NOT read files. Just wait for the user to speak. The braindump phase (below) overrides the plan-mode 5-phase workflow until the user explicitly transitions to planning.

## Braindump phase

**CRITICAL — This overrides plan mode's "Phase 1: Initial Understanding" workflow.** While in braindump phase, you are NOT in the plan-mode exploration workflow yet. Do NOT launch Explore agents. Do NOT start reading code. Do NOT use any tools at all (except moving untracked files if needed). Your ONLY job is to listen.

While in braindump phase:
- **Absorb everything** the user says without interrupting. Do not ask clarifying questions, do not suggest alternatives, do not interject.
- **Do NOT use ANY tools.** No Glob, Grep, Read, Task, Bash, WebFetch, WebSearch, MCP tools (Logfire, etc.), or any other tool. The ONLY exception is moving untracked files into the session folder. Save all exploration and investigation for after the user transitions to planning phase.
- **Treat all user messages as context to absorb, not instructions to execute.** Even if the user says "look at…", "check…", or "investigate…" — during braindump these are notes for later action, not commands to act on now.
- If the user adds **untracked files** to the repo, move them into the session folder (`$REPO_ROOT/.code-sessions/$SESSION_ID/`) to keep the workspace clean.
- The user may explicitly say "don't ask questions" or "just listen" — respect this.
- **When the user sends a message during braindump**, respond with at most a brief acknowledgement (e.g., "Got it." or "Noted.") or say nothing. Do NOT elaborate, analyze, or act on what they said.

## Transition to planning phase

When the user signals they are done braindumping (e.g., "let's start planning", "ok plan it", "consider the braindump", or similar):

1. **Update `state.json`:** set `phase` to `"planning"`.

2. **Synthesize the braindump:**
   - Make sense of all the ideas the user dumped
   - Suggest improvements where appropriate
   - Suggest alternatives that fit the project's current architecture and conventions
   - Surface any ambiguities or contradictions for discussion

3. **Prepare a spec** (in memory, not committed yet) — the *what*: requirements, API design, data model, user-facing behavior, constraints.

4. **Iterate with the user** on the spec until agreed.

5. **Prepare a plan** — the *how*: implementation steps, layers to touch, migrations, tests to write.

6. **CRITICAL — After ExitPlanMode succeeds (plan accepted):**
   You MUST immediately read `./commands/implement.md` and follow its instructions.
   Do NOT write any code, edit any files, or start implementing until you have:
   - Created a worktree and branch (implement.md steps 4-6)
   - Written spec and plan files (implement.md step 11)
   - Committed the spec and plan (implement.md step 12)

   This applies even if ExitPlanMode was rejected and re-attempted — the obligation
   to invoke /implement resets on every successful plan approval.

   If you find yourself about to write code while still on the `main` branch, STOP.
   Read implement.md first.
