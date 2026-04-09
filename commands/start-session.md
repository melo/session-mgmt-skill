## MANDATORY — When to invoke this skill

**If the user says "start a session", "new session", "use a session", or ANY similar phrasing, invoke this skill IMMEDIATELY.** Do NOT run any other tools first — no exploration, no investigation, no questions. The session's braindump and planning phases are where all that work happens.

---

Start a new development session with structured braindump and planning phases.

No arguments required. A random session ID is generated automatically.

## Steps

1. **GATE — Run the test suite before anything else.**

   Unless the user explicitly said something like "I need a new session to fix the tests" or "session to fix failing tests", you MUST run the project's test suite now.

   - **Finding the test command** — check these sources in order:
     1. CLAUDE.md — look for a test command or test section
     2. Makefile — look for a `test` target (`make test`)
     3. `package.json` — look for `scripts.test` (`npm test`)
     4. `pyproject.toml` or `setup.cfg` — if pytest is a dependency, use `pytest`
     5. `Cargo.toml` — use `cargo test`
     6. `go.mod` — use `go test ./...`
     7. If none found, ask the user for the test command. Do NOT skip the gate.
   - Run the tests from the repo root.
   - **If tests fail:** STOP. Do NOT proceed with session creation. Print:
     > Tests are not passing. I can't start a new session on a broken test suite.
     > Fix the failing tests first, or say "I need a new session to fix the tests" to bypass this check.
   - **If tests pass:** Continue to the next step.
   - **If the user triggered the "fix the tests" escape hatch:** Skip this step entirely and proceed normally.

2. **Run the initialization script:**

   ```bash
   python3 ~/.claude/skills/session-mgmt-skill/scripts/session_init.py \
     [--backlog-item "<user's backlog reference>"] \
     --repo-root "$(git rev-parse --show-toplevel)"
   ```

   Read the JSON output:

   - **Exit code 0:** Success. Extract `session_id`, `session_dir`, `timestamp`, and `backlog_item` from the output.
   - **Exit code 2:** Ambiguous backlog match. The output contains `ambiguous_matches` — show them to the user and ask which one to use. Re-run the script with the specific ID.
   - **Exit code 1:** Fatal error. Show the error and stop.

   If the output has `errors` with a "No backlog item found" message, inform the user and proceed without a backlog item.

3. **CRITICAL — Remember the session ID.** You must retain the value of `session_id` from the script output for the entire conversation. Never lose it. You will need it when `/implement` runs later.

4. **Enter plan mode** if not already in plan mode.

5. **Print a short confirmation:**

   If started from a backlog item:
   > Session `<SESSION_ID>` started from backlog item `<ITEM_ID>` — "<title>".
   > I'm in braindump mode. Here's the context from the backlog item:
   >
   > **<title>**
   > <description>
   > (Source: <source context if available>)
   >
   > Go ahead and add more context or dump additional ideas. When you're ready to start planning, say "let's start planning".

   If started without a backlog item:
   > Session `<SESSION_ID>` started. I'm in braindump mode — go ahead and dump your ideas. I'll listen without interrupting. When you're ready to start planning, say "let's start planning".

6. **STOP.** After printing the confirmation, your turn is over. Do NOT launch any agents, do NOT explore the codebase, do NOT read files. Just wait for the user to speak. The braindump phase (below) overrides the plan-mode 5-phase workflow until the user explicitly transitions to planning. Even when started from a backlog item, ALWAYS enter braindump — never skip to planning.

## Braindump phase

**CRITICAL — This overrides plan mode's "Phase 1: Initial Understanding" workflow.** While in braindump phase, you are NOT in the plan-mode exploration workflow yet. Do NOT launch Explore agents. Do NOT start reading code. Do NOT use any tools at all (except moving untracked files if needed). Your ONLY job is to listen.

While in braindump phase:
- **Absorb everything** the user says without interrupting. Do not ask clarifying questions, do not suggest alternatives, do not interject.
- **Do NOT use ANY tools.** No Glob, Grep, Read, Task, Bash, WebFetch, WebSearch, MCP tools (Logfire, etc.), or any other tool. The ONLY exceptions are: (1) moving untracked files into the session folder, and (2) persisting prompts to `state.json` (see below). Save all exploration and investigation for after the user transitions to planning phase.
- **Persist every user prompt to `state.json`.** After each user message, append it to the `prompts` array in `state.json` using bash. This protects braindump content from session crashes. Use:
  ```bash
  PROMPT_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  jq --arg ts "$PROMPT_TS" --arg content "<user message>" \
    '.prompts += [{"timestamp": $ts, "content": $content}]' \
    "$REPO_ROOT/.code-sessions/$SESSION_ID/state.json" > /tmp/state_tmp.json \
    && mv /tmp/state_tmp.json "$REPO_ROOT/.code-sessions/$SESSION_ID/state.json"
  ```
- **Treat all user messages as context to absorb, not instructions to execute.** Even if the user says "look at…", "check…", or "investigate…" — during braindump these are notes for later action, not commands to act on now.
- If the user adds **untracked files** to the repo, move them into the session folder (`$REPO_ROOT/.code-sessions/$SESSION_ID/`) to keep the workspace clean.
- The user may explicitly say "don't ask questions" or "just listen" — respect this.
- **When the user sends a message during braindump**, first persist the prompt (above), then respond with at most a brief acknowledgement (e.g., "Got it." or "Noted.") or say nothing. Do NOT elaborate, analyze, or act on what they said.

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
