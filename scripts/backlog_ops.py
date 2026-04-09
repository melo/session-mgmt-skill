#!/usr/bin/env python3
"""Backlog operations for persistent work item tracking.

All deterministic CRUD operations on the backlog stored in
.code-sessions/backlog/. Each subcommand outputs JSON to stdout.

Usage:
    python3 backlog_ops.py <subcommand> [options] [--repo-root <PATH>]

Subcommands:
    init                                Ensure backlog dir and index exist
    add --title <T> [options]           Add a new item
    list [--include-cancelled]          List items in rank order
    show <id>                           Show item details
    edit <id> --field <F> --value <V>   Edit a field
    rank --id <ID> --position <N>       Move item to position
    rank --id <ID> --above <OTHER_ID>   Move item above another
    link <id1> <id2> --type <T>         Create dependency or reference
    remove <id> [--reason <R>]          Cancel an item
    archive <id> [--docs-dir <PATH>]    Archive a completed item
    update-status <id> --status <S>     Update item status
    resolve-dependency <completed-id>   Move from deps to resolved
    filter [--importance <I>] ...       Filter items

Exit codes:
    0 — success
    1 — error (item not found, filesystem error)
    2 — needs user confirmation (e.g., remove with dependents)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def find_repo_root(hint: str | None = None) -> Path:
    if hint:
        return Path(hint)
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return Path(result.stdout.strip())


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_json(path: Path, data: dict | list):
    tmp_path = path.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.rename(tmp_path, path)


def backlog_dir(repo_root: Path) -> Path:
    return repo_root / ".code-sessions" / "backlog"


def ensure_init(bdir: Path) -> dict:
    """Ensure backlog directory and index.json exist. Returns index."""
    bdir.mkdir(parents=True, exist_ok=True)
    index_path = bdir / "index.json"
    if not index_path.exists():
        atomic_write_json(index_path, {"items": []})
    return json.loads(index_path.read_text())


def load_item(bdir: Path, item_id: str) -> dict | None:
    item_path = bdir / item_id / "item.json"
    if not item_path.exists():
        return None
    return json.loads(item_path.read_text())


def save_item(bdir: Path, item_id: str, item: dict):
    item_path = bdir / item_id / "item.json"
    atomic_write_json(item_path, item)


def save_index(bdir: Path, index: dict):
    atomic_write_json(bdir / "index.json", index)


# --- Subcommands ---

def cmd_init(bdir: Path, _args) -> dict:
    ensure_init(bdir)
    return {"initialized": True, "path": str(bdir)}


def cmd_add(bdir: Path, args) -> dict:
    index = ensure_init(bdir)
    ts = utc_now()
    item_id = os.urandom(3).hex()

    item = {
        "title": args.title,
        "description": args.description or "",
        "importance": args.importance or "medium",
        "dependencies": [],
        "resolved_dependencies": [],
        "references": [],
        "source": json.loads(args.source_json) if args.source_json else {
            "type": "manual",
            "session_id": None,
            "context": None,
            "follow_up_from": None,
        },
        "status": "open",
        "active_session": None,
        "follow_up_items": [],
        "cancelled_reason": None,
        "created_at": ts,
        "updated_at": ts,
        "cancelled_at": None,
    }

    # Create item folder and file
    item_dir = bdir / item_id
    item_dir.mkdir(parents=True, exist_ok=True)
    save_item(bdir, item_id, item)

    # Add to index
    position = args.position
    if position is not None and 0 < position <= len(index["items"]) + 1:
        index["items"].insert(position - 1, item_id)
    else:
        index["items"].append(item_id)
    save_index(bdir, index)

    # Verify atomicity
    index_check = json.loads((bdir / "index.json").read_text())
    if item_id not in index_check["items"]:
        # Retry once
        index_check["items"].append(item_id)
        save_index(bdir, index_check)
        # Check again
        index_check2 = json.loads((bdir / "index.json").read_text())
        if item_id not in index_check2["items"]:
            shutil.rmtree(item_dir, ignore_errors=True)
            return {"error": f"Failed to add {item_id} to index after retry", "created": False}

    rank = index["items"].index(item_id) + 1
    return {"id": item_id, "title": args.title, "rank": rank, "created": True}


def cmd_list(bdir: Path, args) -> dict:
    index = ensure_init(bdir)
    items = []
    for i, item_id in enumerate(index["items"]):
        item = load_item(bdir, item_id)
        if item is None:
            continue
        status = item.get("status", "open")
        if status == "cancelled" and not getattr(args, "include_cancelled", False):
            continue
        blocked_by = [d for d in item.get("dependencies", []) if d not in item.get("resolved_dependencies", [])]
        items.append({
            "rank": i + 1,
            "id": item_id,
            "title": item.get("title", ""),
            "importance": item.get("importance", "medium"),
            "status": status,
            "blocked_by": blocked_by,
            "active_session": item.get("active_session"),
        })
    return {"items": items, "count": len(items)}


def cmd_show(bdir: Path, args) -> dict:
    item_id = args.id
    item = load_item(bdir, item_id)
    if item is None:
        # Try searching by title
        index = ensure_init(bdir)
        for iid in index["items"]:
            candidate = load_item(bdir, iid)
            if candidate and item_id.lower() in candidate.get("title", "").lower():
                return {"id": iid, **candidate}
        return {"error": f"Item '{item_id}' not found"}
    return {"id": item_id, **item}


def cmd_edit(bdir: Path, args) -> dict:
    item = load_item(bdir, args.id)
    if item is None:
        return {"error": f"Item '{args.id}' not found"}

    # Parse value as JSON if possible, otherwise use as string
    try:
        value = json.loads(args.value)
    except (json.JSONDecodeError, TypeError):
        value = args.value

    item[args.field] = value
    item["updated_at"] = utc_now()
    save_item(bdir, args.id, item)
    return {"id": args.id, "field": args.field, "updated": True}


def cmd_rank(bdir: Path, args) -> dict:
    index = ensure_init(bdir)
    item_id = args.id

    if item_id not in index["items"]:
        return {"error": f"Item '{item_id}' not in index"}

    index["items"].remove(item_id)

    if args.above:
        if args.above not in index["items"]:
            return {"error": f"Target item '{args.above}' not in index"}
        target_pos = index["items"].index(args.above)
        index["items"].insert(target_pos, item_id)
    elif args.position is not None:
        pos = max(0, min(args.position - 1, len(index["items"])))
        index["items"].insert(pos, item_id)
    else:
        index["items"].append(item_id)

    save_index(bdir, index)
    new_rank = index["items"].index(item_id) + 1
    return {"id": item_id, "new_rank": new_rank, "ranked": True}


def cmd_link(bdir: Path, args) -> dict:
    item1 = load_item(bdir, args.id1)
    item2 = load_item(bdir, args.id2)
    if item1 is None:
        return {"error": f"Item '{args.id1}' not found"}
    if item2 is None:
        return {"error": f"Item '{args.id2}' not found"}

    ts = utc_now()
    link_type = args.type

    if link_type == "dependency":
        # id2 depends on id1 (id1 blocks id2)
        if args.id1 not in item2.get("dependencies", []):
            item2.setdefault("dependencies", []).append(args.id1)
            item2["updated_at"] = ts
            save_item(bdir, args.id2, item2)
    elif link_type == "reference":
        # Bidirectional reference
        if args.id2 not in item1.get("references", []):
            item1.setdefault("references", []).append(args.id2)
            item1["updated_at"] = ts
            save_item(bdir, args.id1, item1)
        if args.id1 not in item2.get("references", []):
            item2.setdefault("references", []).append(args.id1)
            item2["updated_at"] = ts
            save_item(bdir, args.id2, item2)

    return {"id1": args.id1, "id2": args.id2, "type": link_type, "linked": True}


def cmd_remove(bdir: Path, args) -> dict:
    item = load_item(bdir, args.id)
    if item is None:
        return {"error": f"Item '{args.id}' not found"}

    # Check for dependents
    index = ensure_init(bdir)
    dependents = []
    for iid in index["items"]:
        if iid == args.id:
            continue
        other = load_item(bdir, iid)
        if other and args.id in other.get("dependencies", []):
            dependents.append({"id": iid, "title": other.get("title", "")})

    if dependents:
        # Exit code 2: needs user confirmation
        print(json.dumps({
            "id": args.id,
            "title": item.get("title", ""),
            "dependents": dependents,
            "needs_confirmation": True,
        }))
        sys.exit(2)

    ts = utc_now()
    item["status"] = "cancelled"
    item["cancelled_reason"] = args.reason
    item["cancelled_at"] = ts
    item["updated_at"] = ts
    save_item(bdir, args.id, item)

    # Remove from index
    if args.id in index["items"]:
        index["items"].remove(args.id)
        save_index(bdir, index)

    return {"id": args.id, "title": item.get("title", ""), "removed": True}


def cmd_archive(bdir: Path, args) -> dict:
    item = load_item(bdir, args.id)
    if item is None:
        return {"error": f"Item '{args.id}' not found"}

    ts = utc_now()
    item["status"] = "archived"
    item["updated_at"] = ts
    save_item(bdir, args.id, item)

    # Move to docs dir if specified
    moved_to = None
    if args.docs_dir:
        docs_dir = Path(args.docs_dir)
        dest = docs_dir / f"backlog-item-{args.id}"
        src = bdir / args.id
        if src.is_dir():
            shutil.move(str(src), str(dest))
            moved_to = str(dest)

    # Remove from index
    index = ensure_init(bdir)
    if args.id in index["items"]:
        index["items"].remove(args.id)
        save_index(bdir, index)

    return {"id": args.id, "archived": True, "moved_to": moved_to}


def cmd_update_status(bdir: Path, args) -> dict:
    item = load_item(bdir, args.id)
    if item is None:
        return {"error": f"Item '{args.id}' not found"}

    ts = utc_now()
    item["status"] = args.status
    item["updated_at"] = ts
    if args.session_id:
        item["active_session"] = args.session_id
    if args.status == "open":
        item["active_session"] = None
    save_item(bdir, args.id, item)
    return {"id": args.id, "status": args.status, "updated": True}


def cmd_resolve_dependency(bdir: Path, args) -> dict:
    """Move completed_id from dependencies to resolved_dependencies in all items."""
    index = ensure_init(bdir)
    completed_id = args.completed_id
    affected = []

    for iid in index["items"]:
        item = load_item(bdir, iid)
        if item is None:
            continue
        deps = item.get("dependencies", [])
        if completed_id in deps:
            deps.remove(completed_id)
            item.setdefault("resolved_dependencies", []).append(completed_id)
            item["updated_at"] = utc_now()
            save_item(bdir, iid, item)
            unblocked = len(deps) == 0
            affected.append({"id": iid, "title": item.get("title", ""), "unblocked": unblocked})

    return {"completed_id": completed_id, "affected_items": affected}


def cmd_filter(bdir: Path, args) -> dict:
    index = ensure_init(bdir)
    items = []

    for i, item_id in enumerate(index["items"]):
        item = load_item(bdir, item_id)
        if item is None:
            continue

        status = item.get("status", "open")
        importance = item.get("importance", "medium")
        deps = item.get("dependencies", [])
        resolved = item.get("resolved_dependencies", [])
        unresolved = [d for d in deps if d not in resolved]

        # Apply filters
        if args.importance and importance != args.importance:
            continue
        if args.status and status != args.status:
            continue
        if args.blocked and not unresolved:
            continue
        if args.unblocked and unresolved:
            continue
        if status == "cancelled" and not args.status == "cancelled":
            continue

        items.append({
            "rank": i + 1,
            "id": item_id,
            "title": item.get("title", ""),
            "importance": importance,
            "status": status,
            "blocked_by": unresolved,
        })

    return {"items": items, "count": len(items)}


def main():
    parser = argparse.ArgumentParser(description="Backlog operations")
    parser.add_argument("--repo-root", help="Repository root path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    subparsers.add_parser("init")

    # add
    add_p = subparsers.add_parser("add")
    add_p.add_argument("--title", required=True)
    add_p.add_argument("--description", "--desc")
    add_p.add_argument("--importance", choices=["critical", "high", "medium", "low"])
    add_p.add_argument("--position", type=int)
    add_p.add_argument("--source-json", help="JSON string for source metadata")

    # list
    list_p = subparsers.add_parser("list")
    list_p.add_argument("--include-cancelled", action="store_true")

    # show
    show_p = subparsers.add_parser("show")
    show_p.add_argument("id")

    # edit
    edit_p = subparsers.add_parser("edit")
    edit_p.add_argument("id")
    edit_p.add_argument("--field", required=True)
    edit_p.add_argument("--value", required=True)

    # rank
    rank_p = subparsers.add_parser("rank")
    rank_p.add_argument("--id", required=True)
    rank_p.add_argument("--position", type=int)
    rank_p.add_argument("--above")

    # link
    link_p = subparsers.add_parser("link")
    link_p.add_argument("id1")
    link_p.add_argument("id2")
    link_p.add_argument("--type", required=True, choices=["dependency", "reference"])

    # remove
    remove_p = subparsers.add_parser("remove")
    remove_p.add_argument("id")
    remove_p.add_argument("--reason")

    # archive
    archive_p = subparsers.add_parser("archive")
    archive_p.add_argument("id")
    archive_p.add_argument("--docs-dir")

    # update-status
    status_p = subparsers.add_parser("update-status")
    status_p.add_argument("id")
    status_p.add_argument("--status", required=True, choices=["open", "in-progress", "archived", "cancelled"])
    status_p.add_argument("--session-id")

    # resolve-dependency
    resolve_p = subparsers.add_parser("resolve-dependency")
    resolve_p.add_argument("completed_id")

    # filter
    filter_p = subparsers.add_parser("filter")
    filter_p.add_argument("--importance", choices=["critical", "high", "medium", "low"])
    filter_p.add_argument("--status", choices=["open", "in-progress", "archived", "cancelled"])
    filter_p.add_argument("--blocked", action="store_true")
    filter_p.add_argument("--unblocked", action="store_true")

    args = parser.parse_args()

    try:
        repo_root = find_repo_root(args.repo_root)
    except subprocess.CalledProcessError:
        print(json.dumps({"error": "Not a git repository"}))
        sys.exit(1)

    bdir = backlog_dir(repo_root)

    commands = {
        "init": cmd_init,
        "add": cmd_add,
        "list": cmd_list,
        "show": cmd_show,
        "edit": cmd_edit,
        "rank": cmd_rank,
        "link": cmd_link,
        "remove": cmd_remove,
        "archive": cmd_archive,
        "update-status": cmd_update_status,
        "resolve-dependency": cmd_resolve_dependency,
        "filter": cmd_filter,
    }

    handler = commands.get(args.command)
    if not handler:
        print(json.dumps({"error": f"Unknown command: {args.command}"}))
        sys.exit(1)

    result = handler(bdir, args)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
