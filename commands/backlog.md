Manage the project backlog: a persistent, stack-ranked list of work items stored in `.code-sessions/backlog/`.

## Dispatch

This command handles explicit subcommands AND natural language. When the user mentions "backlog" in conversation (e.g., "add this to the backlog", "what's in the backlog?", "move the webhook item above auth"), route to the appropriate subcommand below.

**During an active session:** If the user says something like "we can improve X later, add to backlog", capture the item with session context automatically (see `/backlog add` below).

### Subcommand routing

| User intent | Action |
|---|---|
| List items ("show me the backlog", "what's in the backlog?", `/backlog`) | → List |
| Add item ("add to backlog", "backlog this", `/backlog add`) | → Add |
| Show details (`/backlog show <id>`) | → Show |
| Edit item (`/backlog edit <id>`) | → Edit |
| Reorder ("move X above Y", `/backlog rank`) | → Rank |
| Link items (`/backlog link <id> <id>`) | → Link |
| Remove/cancel item ("forget that backlog item", `/backlog remove <id>`) | → Remove |
| Filter ("show me high importance items", `/backlog filter`) | → Filter |

---

## Storage initialization

Before any operation, ensure the backlog directory and index exist:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
BACKLOG_DIR="$REPO_ROOT/.code-sessions/backlog"
mkdir -p "$BACKLOG_DIR"
```

If `$BACKLOG_DIR/index.json` does not exist, create it:
```bash
echo '{"items":[]}' > "$BACKLOG_DIR/index.json"
```

---

## `/backlog` — List

Read `index.json` to get the ordered list of IDs. For each ID, read `<id>/item.json`.

Display as a ranked table:

```
# Project Backlog (N items)

 #  | ID     | Title                          | Importance | Status
----|--------|--------------------------------|------------|--------
 1  | abc123 | Add retry logic to webhooks    | high       | open
 2  | def456 | Refactor auth middleware        | medium     | blocked by [ghi789]
 3  | ghi789 | Update API docs                | low        | in-progress (session: 20260408-916fc9)
```

**Rules:**
- Only show items in the index (i.e., `open` and `in-progress`). Cancelled items are never shown here.
- Items with non-empty `dependencies` array are marked as "blocked by [dep-ids]".
- Items with `status: "in-progress"` show the `active_session` ID.
- If the backlog is empty, print: "Backlog is empty. Use `/backlog add` to create an item."

---

## `/backlog add`

Create a new backlog item.

### 1. Generate ID

```bash
ITEM_ID=$(openssl rand -hex 3)
```

### 2. Gather item details

If the user provided details inline (e.g., "add to backlog: retry logic for webhooks"), extract title and description from their message.

If the user said something vague (e.g., "add that to the backlog"), ask for at least a title.

For importance, ask the user or default to `medium` if not specified.

### 3. Detect session context

Check if there is an active session. Look for `.code-sessions/current/state.json` in the current workspace, or scan `.code-sessions/*/state.json` for a session with phase `braindump`, `planning`, or `implementing`.

If an active session exists, auto-populate the source:
```json
{
  "type": "session",
  "session_id": "<active-session-id>",
  "context": "<brief description of what the session is working on and why this item came up>"
}
```

If no active session, use:
```json
{
  "type": "standalone",
  "session_id": null,
  "context": null
}
```

### 4. Create the item folder and file

```bash
mkdir -p "$BACKLOG_DIR/$ITEM_ID"
```

Write `$BACKLOG_DIR/$ITEM_ID/item.json`:
```json
{
  "id": "<ITEM_ID>",
  "title": "<title>",
  "description": "<description>",
  "importance": "<critical|high|medium|low>",
  "dependencies": [],
  "resolved_dependencies": [],
  "references": [],
  "source": { ... },
  "status": "open",
  "active_session": null,
  "follow_up_items": [],
  "cancelled_reason": null,
  "created_at": "<UTC timestamp via bash>",
  "updated_at": "<UTC timestamp via bash>",
  "cancelled_at": null
}
```

Capture timestamps via bash:
```bash
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

### 5. Append to index

Read `index.json`, append the new ID to the `items` array (end of list = lowest rank), write back.

Unless the user specified a position (e.g., "add to the top of the backlog"), in which case insert at the specified position.

### 6. Confirm

Print a short confirmation:
> Added to backlog: `<ITEM_ID>` — "<title>" (importance: <importance>, rank: #<position>)

---

## `/backlog show <id>`

Read `$BACKLOG_DIR/<id>/item.json` and display all fields in a readable format.

If the user references an item by title or description instead of ID, search through all items to find a match.

**Display:**
- All metadata fields
- Dependencies: show title + ID of each, and whether resolved or active
- Resolved dependencies: show what was completed
- References: show title + ID of each
- Follow-up items: show title + ID of each (if any)
- Source context: show where this item came from
- Attachments: list files in the item folder (excluding `item.json`)

---

## `/backlog edit <id>`

Modify fields on an existing item. The user says what to change (e.g., "change importance to high", "update the description to...").

After editing, update `updated_at` with a fresh timestamp:
```bash
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

Write the updated `item.json`.

---

## `/backlog rank`

Reorder items in the index. The user gives instructions like:
- "move X above Y"
- "X before Y"
- "X is more important than Y"
- "move X to the top"
- "move X to position 3"

Resolve X and Y by ID or title. Update `index.json` accordingly.

Print the updated backlog list (same format as `/backlog` list) to confirm the new order.

---

## `/backlog link <id> <id>`

Create a relationship between two items. Ask the user which type:

- **Dependency:** "A depends on B" → add B's ID to A's `dependencies` array
- **Reference:** "A is related to B" → add B's ID to A's `references` array AND add A's ID to B's `references` array (bidirectional)

If the user's phrasing makes the type clear (e.g., "X blocks Y" → Y depends on X), don't ask.

Update `updated_at` on all modified items.

---

## `/backlog remove <id>`

Cancel a backlog item.

### 1. Find the item

Resolve by ID or title.

### 2. Check for dependents

Read all items in the index. If any have this item's ID in their `dependencies`, warn the user:
> "The following items depend on this one: <list>. Removing it will leave them with an unresolved dependency. Continue?"

If the user says no, **STOP**.

### 3. Update the item

```bash
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

Set:
- `status`: `"cancelled"`
- `cancelled_at`: `$TS`
- `cancelled_reason`: user's reason if provided, otherwise `null`
- `updated_at`: `$TS`

### 4. Remove from index

Read `index.json`, remove the ID from the `items` array, write back.

The item folder stays in `backlog/<id>/` for history.

### 5. Confirm

> Removed from backlog: `<ITEM_ID>` — "<title>"
> (Reason: <reason or "none provided">)

---

## `/backlog filter`

List items with filters. Filters can be specified as arguments or natural language:

- **importance:** `/backlog filter importance:high` or "show me critical backlog items"
- **status:** `/backlog filter status:cancelled` or "show me cancelled items"
  - **IMPORTANT:** Cancelled items are ONLY shown when the user explicitly asks for them. Never include them in default listings.
- **blocked:** `/backlog filter blocked` — items with non-empty `dependencies`
- **unblocked:** `/backlog filter unblocked` — items with empty `dependencies`

Display uses the same table format as `/backlog` list.

When filtering by `status:cancelled`, scan all item folders in `backlog/` (not just the index) since cancelled items are removed from the index.

---

## Creating follow-up items

When follow-up items are created at end-session time (the user says "end session, we should follow up with X and Y"), use `/backlog add` logic with these specifics:

- `source.type`: `"follow-up"`
- `source.follow_up_from`: ID of the item that was just archived
- `source.session_id`: the ending session's ID
- `source.context`: brief description of what was completed and why follow-up is needed

After creating follow-up items, update the archived parent item's `follow_up_items` array with the new IDs.
