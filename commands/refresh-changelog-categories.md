# Refresh Changelog Categories

Generate or refresh the `.claude/changelog-categories.yml` file by analyzing the project's directory structure.

No arguments required.

## Steps

### 1. Run the refresh script

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
python3 ~/.claude/skills/session-mgmt-skill/scripts/refresh_categories.py --repo-root "$REPO_ROOT"
```

The script handles all mechanical work:

- Scans the project's directory structure for common patterns (APIs, frontend, database, infrastructure, tests, docs, etc.)
- Reads the existing `.claude/changelog-categories.yml` if present and preserves manual customizations
- Merges inferred categories with existing ones
- Writes the updated YAML config

Read the JSON output:

- `categories`: the full category map (category name → list of path prefixes)
- `preserved_from_existing`: categories that were kept from the existing config but not inferred from the directory structure
- `config_path`: absolute path to the written file
- `written`: true if the file was written

**GATE:** Verify the script exited with code 0. If it failed, show the error and stop.

### 2. Review with the user

Show the user the generated file and ask if they want to adjust anything:

```bash
cat "$REPO_ROOT/.claude/changelog-categories.yml"
```

If the user requests changes, edit the file directly. The next refresh will preserve their manual additions.
