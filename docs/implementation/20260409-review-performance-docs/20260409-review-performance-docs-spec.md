# Spec: Session-Mgmt-Skill Review, Performance, and Documentation

## Summary

A comprehensive pass over the session-mgmt-skill covering three areas: correctness/consistency of all command files, performance optimization by packaging deterministic sequences into Python scripts, and documentation updates to the README.

## Requirements

### 1. Command File Consistency

- Every command file must have deterministic gates between steps: a verifiable condition that must be true before proceeding.
- All error paths must be explicit: what happens when a step fails, what options the user has, what state is left behind.
- Remove ambiguous language that the LLM could misinterpret (e.g., "if you recognize this change").
- Fix known inconsistencies: worktree paths, state.json phase ordering, macOS date compatibility.
- Adopt Claude Code best practices for worktree location (`.claude/worktrees/<branch>`) and gitignored file copying (`.worktreeinclude`).

### 2. Performance — Python Script Packaging

- Package multi-step deterministic bash/jq sequences into Python scripts that execute in one shot.
- Scripts output structured JSON to stdout; progress/errors to stderr.
- Scripts use stdlib only (no external dependencies beyond what's already installed).
- Atomic file writes: write to `.tmp` in the same directory, then `os.rename()`.
- Exit codes: 0=success, 1=fatal error, 2=needs user input (ambiguity, confirmation).
- The LLM's role reduces to: running the script, reading the JSON, making judgment calls, and interacting with the user.

### 3. README Documentation

- Remove alpha label; add stability statement.
- Add "What about Superpowers?" section explaining the relationship to Claude Code's built-in feature.
- Document the backlog feature (commands, storage, workflow integration).
- Document state transitions in detail.
- Document quick-check mode for daily-changes.
- Update file trees to include new commands and scripts.
- Fix worktree path documentation to match implementation.
- Convert the workflow ASCII diagram to an inline SVG.

## Constraints

- No external Python dependencies beyond stdlib (and what setup.md already installs).
- Maintain backward compatibility with existing `.code-sessions/` state.json files (treat missing fields as null/default).
- All scripts must work on both macOS and Linux.
- Keep command files self-contained and readable — they are the primary interface for the LLM.
