# 03 — Project Management

Guild can manage multiple projects and repositories simultaneously. A project is any codebase the Guild is aware of — heroes can be dispatched to any registered project, and Guild Master maintains separate memory and context per project.

---

## Project Schema

```sql
CREATE TABLE projects (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,     -- e.g. "greentic"
  display_name    TEXT NOT NULL,            -- e.g. "Greentic AI"
  path            TEXT NOT NULL,            -- absolute local path
  repo_url        TEXT,                     -- GitHub/GitLab remote URL
  repo_provider   TEXT,                     -- "github" | "gitlab" | "none"
  main_branch     TEXT DEFAULT 'main',
  dev_branch      TEXT DEFAULT 'development',
  language        TEXT,                     -- primary language detected on register
  status          TEXT DEFAULT 'active',    -- active | paused | archived
  default_mcps    JSON DEFAULT '[]',        -- MCP IDs always attached for this project
  created_at      DATETIME NOT NULL,
  last_active     DATETIME
);
```

---

## Registering a Project

### From CLI

```bash
# Interactive registration
guild project add

# With flags (non-interactive)
guild project add \
  --path ./my-repo \
  --name greentic \
  --provider github \
  --main main \
  --dev development
```

### Registration Sequence

```
1. Validate path exists and is a git repository
2. Detect primary language from file extensions
3. Read existing conventions if present (.editorconfig, .eslintrc, etc.)
4. Check if dev_branch exists — create from main if not
5. Configure branch protection rules via provider API (if configured)
6. Create shared memory template: memory/shared/projects/{name}.md
7. Create project entry in guild.db
8. Scan for existing TODOs, open issues — offer to create quests
9. Report summary to developer
```

### What Gets Created on Register

```
memory/shared/projects/{name}.md      ← project knowledge base (starts with detected conventions)
memory/shared/projects/{name}-adr/    ← folder for this project's ADRs
workspace/quests/                     ← quest files scoped to project
```

---

## Project Configuration

### View and Edit

```bash
# View project details
guild project show greentic

# Edit configuration interactively
guild project edit greentic

# Set default MCPs for a project
guild project mcp add greentic databricks-mcp
guild project mcp remove greentic databricks-mcp
guild project mcp list greentic

# Set preferred heroes for a project
guild project hero prefer greentic StormForge
guild project hero list greentic
```

### Project Config File

Each project has a config section in `guild.db` plus a human-readable summary at `workspace/projects/{name}/config.md`:

```markdown
# Project: greentic
Path: /home/user/projects/greentic
Provider: GitHub | Repo: maarten-ectors/greentic
Main branch: main | Dev branch: development
Language: Rust
Status: active

## Default MCPs
- github-mcp
- filesystem (built-in)
- git (built-in)

## Preferred Heroes
- StormForge (Rust Sorcerer) — 14 quests completed here

## Branch Protection
- main: human approval required ✓
- development: hero reviewer + tests ✓

## Registered: 2026-03-01 | Last active: 2026-03-06
```

---

## Multi-Repo Projects

Some projects span multiple repositories (e.g., monorepo split, frontend + backend). Guild supports grouping repos under one project:

```bash
# Create a project group
guild project group create "MAP Group Platform"

# Add repos to the group
guild project group add "MAP Group Platform" ./map-backend
guild project group add "MAP Group Platform" ./map-frontend
guild project group add "MAP Group Platform" ./map-reporting

# View group
guild project group show "MAP Group Platform"
```

### Group Behavior

- Guild Master treats the group as one logical project
- Shared memory is shared across all repos in the group: `memory/shared/projects/map-group-platform.md`
- Each repo still has its own branch workflow
- Heroes can be assigned quests that span repos in the same group (multi-repo quest)
- Quest chain for cross-repo quests: each repo gets its own branch and PR, but they are linked under one chain ID

---

## Multi-Repo Quest Example

```
Goal: "Sync MAP backend API changes with frontend types"

Guild Master decomposes into:
  Chain GLC-020 (cross-repo)
  ├── GLD-060 [RARE]  Update API response types in map-backend
  │   Branch: feature/GLD-060-api-types (map-backend repo)
  │   Assigned: Node Assassin
  │
  ├── GLD-061 [RARE]  Update TypeScript interfaces in map-frontend
  │   Branch: feature/GLD-061-ts-interfaces (map-frontend repo)
  │   Assigned: Frontend Archer
  │   Depends on: GLD-060 (waits for backend types to be finalized)
  │
  ├── GLD-062 [COMMON] Test both repos compile together
  │   Assigned: Python Sage
  │
  └── GLD-063 [COMMON] Review both PRs
      Assigned: Node Assassin (different from GLD-061 implementor)
```

---

## Pausing and Archiving Projects

```bash
# Pause — heroes won't be assigned quests for this project
# Existing active quests finish, no new quests assigned
guild project pause greentic

# Resume paused project
guild project resume greentic

# Archive — project is read-only, memory preserved, no new quests
guild project archive greentic

# Unarchive
guild project unarchive greentic

# Remove — deletes project from guild (does NOT delete local files or repo)
# Asks for confirmation, warns if active quests exist
guild project remove greentic
```

### Pause vs Archive vs Remove

| Action | Active quests | New quests | Memory | Repo files |
|---|---|---|---|---|
| Pause | Finish current | Blocked | Preserved | Untouched |
| Archive | Blocked immediately | Blocked | Preserved (read-only) | Untouched |
| Remove | Cancelled | N/A | Deleted from guild | Untouched |

---

## Project Health Dashboard

Guild Master runs a weekly health scan per project (see Section 06). Summary accessible via:

```bash
guild project health greentic
```

Output:

```
Project Health: greentic
Last scan: 2026-03-06 08:00

CODE HEALTH
  Open TODOs:        3  (2 new this week)
  Test coverage:     84%  (↓ 2% from last week) ⚠
  Failing tests:     0  ✓
  Outdated deps:     2  (1 with known vulnerability) ⚠

QUEST ACTIVITY (last 30 days)
  Completed:         18 quests
  Avg completion:    2h 14m
  Most active hero:  StormForge (11 quests)

MEMORY
  Shared memory:     4.2KB
  ADRs:              3 decisions recorded
  Last updated:      2 days ago

OPEN ITEMS
  ⚠ Test coverage dropped below 85% threshold
  ⚠ lodash@4.17.20 has known vulnerability — CVE-2021-23337
  → 2 auto-created chore quests in backlog
```

---

## Project-Scoped Goals

When a developer has multiple projects registered, they can scope goals:

```bash
# Scoped to specific project
guild goal --project greentic "Refactor WASM adapters"

# Guild Master infers project from context
guild goal "Fix the rate limiter bug"
# → Guild Master checks recent activity, asks if unclear

# Goal spanning multiple projects
guild goal --project "MAP Group Platform" "Sync API types between backend and frontend"
```

If no `--project` flag and Guild Master cannot infer project from goal description with >85% confidence, it asks via Telegram or CLI prompt before decomposing.
