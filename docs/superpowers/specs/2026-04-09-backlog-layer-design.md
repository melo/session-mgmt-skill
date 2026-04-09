# Backlog Layer for Session Management Skill

**Date:** 2026-04-09
**Status:** Draft

## Problem

The session-mgmt skill operates at a single level: one session covers braindump → planning → implementation → end. There's no persistent place to capture ideas, track planned work, or manage dependencies between future tasks. Ideas that come up during a session ("we should improve X later") get lost unless manually noted elsewhere.

## Solution

A persistent backlog layer that lives alongside sessions in `.code-sessions/backlog/`. It serves as a stack-ranked list of work items that can be populated standalone or as overflow from active sessions, and pulled into sessions when ready.

## Storage Layout

```
.code-sessions/
├── backlog/
│   ├── index.json              # Ordered array of item IDs (position = rank)
│   ├── <id>/
│   │   ├── item.json           # Item metadata
│   │   └── <attachments...>    # Any files relevant to the item
│   └── ...
├── <session-id>/               # Existing session folders (unchanged)
│   └── state.json
```

### index.json

A single ordered array. Position is priority — item at index 0 is highest rank.

```json
{
  "items": ["abc123", "def456", "ghi789"]
}
```

Items with status `open` or `in-progress` remain in the index (preserving rank position). They are only removed from the index when `archived` (successful end-session) or `cancelled`.

### item.json

```json
{
  "id": "abc123",
  "title": "Add retry logic to webhook delivery",
  "description": "Webhooks silently fail on timeout. Need exponential backoff with configurable max retries.",
  "importance": "high",
  "dependencies": ["def456"],
  "resolved_dependencies": [],
  "references": ["ghi789"],
  "source": {
    "type": "session",
    "session_id": "20260408-916fc9",
    "context": "While implementing webhook endpoints, noticed delivery has no retry mechanism"
  },
  "status": "open",
  "active_session": null,
  "cancelled_reason": null,
  "created_at": "2026-04-08T22:30:00Z",
  "updated_at": "2026-04-08T22:30:00Z",
  "cancelled_at": null
}
```

**Fields:**

| Field | Type | Description |
|---|---|---|
| `id` | string | 6-char hex, same style as session IDs |
| `title` | string | Brief summary |
| `description` | string | Detailed context |
| `importance` | enum | `critical`, `high`, `medium`, `low` |
| `dependencies` | string[] | IDs of items that must be completed first |
| `resolved_dependencies` | string[] | IDs of dependencies that were completed (audit trail) |
| `references` | string[] | IDs of related items (informational, non-blocking) |
| `source.type` | enum | `standalone`, `session`, `follow-up` |
| `source.session_id` | string? | Session ID if created during a session |
| `source.context` | string? | What was happening when this item was captured |
| `source.follow_up_from` | string? | ID of the completed item this follows up on |
| `status` | enum | `open`, `in-progress`, `archived`, `cancelled` |
| `active_session` | string? | Session ID currently working on this item |
| `follow_up_items` | string[] | IDs of backlog items created as follow-ups when this item was archived |
| `cancelled_reason` | string? | Optional reason for cancellation |
| `created_at` | ISO 8601 | Creation timestamp |
| `updated_at` | ISO 8601 | Last modification timestamp |
| `cancelled_at` | ISO 8601? | When the item was cancelled |

## Commands

### Dispatch

A new `backlog` command file added to the skill. SKILL.md updated to route `/backlog` and natural language containing "backlog" to this command.

### Explicit Subcommands

| Command | Action |
|---|---|
| `/backlog` | List all open items in rank order (summary view) |
| `/backlog add` | Create new item (interactive or inline) |
| `/backlog show <id>` | View full item details, attachments, and dependency graph |
| `/backlog edit <id>` | Modify item fields |
| `/backlog rank` | Reorder items ("move X above Y", "X before Y") |
| `/backlog link <id> <id>` | Create dependency or reference between items |
| `/backlog remove <id>` | Cancel an item (with optional reason) |
| `/backlog filter` | List with filters (importance, status, has-deps, blocked/unblocked) |

### Natural Language Triggers

Any mention of "backlog" in conversation context (e.g., "add this to the backlog", "what's in the backlog?", "move the webhook item above auth") routes through the same command logic. When used during an active session, session context is auto-captured in the item's `source` field.

## Lifecycle & State Transitions

```
                    ┌─────────────────────────────────┐
                    │                                  │
                    v                                  │
  [created] ──► open ──► in-progress ──► archived      │
                 │            │                        │
                 │            └──── (cancel session) ──┘
                 │
                 └──► cancelled
```

### Creation

**Standalone** (`/backlog add` outside a session):
- User braindumps the idea, Claude structures it into `item.json`
- `source.type: "standalone"`
- Appended to end of index (lowest rank) unless user specifies position

**In-session** ("add to backlog" during active session):
- Claude captures the item plus session context automatically
- `source.type: "session"`, `source.session_id`, `source.context` populated
- Context includes: what the session is working on and why this item came up

**Follow-up** (user specifies follow-ups at `/end-session`):
- Created with `source.type: "follow-up"` and `source.follow_up_from` referencing the completed item
- User explicitly tells Claude follow-ups at end-session time (e.g., "end session, we should follow up with X and Y")
- Claude does NOT prompt for follow-ups

### Pulling Into a Session

1. User says `/start-session` and references a backlog item (by ID, title, or description)
2. Item updated: `status: "in-progress"`, `active_session: "<session-id>"`
3. Item's description and context pre-seed the session braindump
4. Session ALWAYS enters braindump phase — never skips to planning, even with a backlog item
5. User explicitly transitions to planning when ready

### Successful End-Session

1. Move `backlog/<id>/` folder → `docs/implementation/<session-name>/backlog-item-<id>/`
2. Set `status: "archived"` in the moved `item.json`
3. Remove the ID from `index.json`
4. For items that had this ID in `dependencies`:
   - Move the ID from `dependencies` to `resolved_dependencies`
   - If follow-up items were created during end-session:
     - Ask the user: should previously-blocked items be unblocked now, or should the new follow-up items be added as dependencies?
   - If no follow-up items: items with now-empty `dependencies` are flagged as "unblocked" in the end-session summary

### Cancelled Session

1. Set `status: "open"`, `active_session: null`
2. Item stays in its original rank position in `index.json`
3. No dependency changes

### Cancelled Backlog Item

1. Set `status: "cancelled"`, `cancelled_at` timestamp, optional `cancelled_reason`
2. Remove from `index.json`
3. Item folder stays in `backlog/<id>/` for history
4. Items that depended on this one get flagged — Claude surfaces a warning and asks user what to do
5. Cancelled items are only shown when the user explicitly asks (e.g., `/backlog filter status:cancelled` or "show me cancelled backlog items") — they never appear in default listings

## Audit Trail: Cross-Referencing Between Objects

All objects (sessions, backlog items) maintain bidirectional links for a complete audit trail:

- **Session → Backlog item:** `state.json` has `backlog_item_id` pointing to the source item
- **Backlog item → Session:** `item.json` has `active_session` pointing to the working session
- **Archived item → Session:** archived `item.json` retains `active_session` as the session that completed it
- **Follow-up item → Parent item:** `source.follow_up_from` links to the completed item that spawned it
- **Parent item → Follow-ups:** when follow-ups are created, add their IDs to a `follow_up_items` field on the archived parent
- **Dependencies → Resolved:** `resolved_dependencies` preserves the link to completed items (never deleted, just moved from `dependencies`)
- **Cancelled item → Reason:** `cancelled_reason` and `cancelled_at` preserve the decision context

This means you can always trace: which session worked on which item, what item spawned what follow-ups, what was completed to unblock what, and why something was cancelled.

## Integration With Existing Commands

### state.json Changes

Add a `backlog_item_id` field (nullable) to session state. Set when a session is started from a backlog item. Used by end-session and cancel-session to know which backlog item to archive or revert.

### start-session.md Changes

- After session creation and before entering braindump, check if user referenced a backlog item
- If yes: update backlog item status, set `state.json.backlog_item_id`, pre-seed braindump with item context
- Always enter braindump phase regardless

### end-session.md Changes

- If session was started from a backlog item:
  - Archive the item folder to `docs/implementation/<session-name>/`
  - Process dependency unblocking (with follow-up awareness as described above)
- Process any follow-up items the user mentioned (create new backlog items)

### cancel-session.md Changes

- If session was started from a backlog item:
  - Revert item to `open` status, clear `active_session`

### SKILL.md Changes

- Add `/backlog` dispatch entry
- Add natural language "backlog" keyword detection
- Document shared concept: backlog storage in `.code-sessions/backlog/`

## Display Formatting

### List View (`/backlog`)

```
# Project Backlog (3 items)

 #  | ID     | Title                          | Importance | Status
----|--------|--------------------------------|------------|--------
 1  | abc123 | Add retry logic to webhooks    | high       | open
 2  | def456 | Refactor auth middleware        | medium     | 🔒 blocked
 3  | ghi789 | Update API docs                | low        | open
```

Blocked items (those with unresolved dependencies) marked with 🔒.
In-progress items show the active session ID.

### Detail View (`/backlog show <id>`)

Shows all fields, dependency/reference graph, source context, and lists attachments.
