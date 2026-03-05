# 13 — Technical Architecture

---

## Technology Stack

| Layer | Technology | Reason |
|---|---|---|
| Core runtime | Rust | Single binary distribution, process management, performance |
| Agent logic | Python | Claude Code SDK most mature in Python |
| Dashboard | React | Bundled into binary, no Node.js required on user machine |
| State | SQLite | Zero-config, portable, single `guild.db` file |
| Memory | Markdown files | Human-readable, git-friendly, inspectable without tooling |

---

## Repository Structure

```
guild/
├── src/                         Rust core
│   ├── main.rs                  CLI entrypoint
│   ├── process_manager.rs       Spawn and monitor hero sessions
│   ├── watcher.rs               Filesystem event watcher
│   ├── ipc.rs                   Inter-process communication
│   ├── db.rs                    SQLite interface
│   └── secrets.rs               Encrypted secrets store
│
├── agents/                      Python agent logic
│   ├── guild_master.py          Orchestrator brain
│   ├── hero_runtime.py          Hero session wrapper
│   ├── memory_manager.py        Read/write memory layer
│   └── mcp_builder.py           MCP config assembly per session
│
├── dashboard/                   React local web UI (bundled at build)
│   └── src/
│       ├── GuildHall.tsx
│       ├── QuestBoard.tsx
│       ├── HeroRoster.tsx
│       └── MemoryViewer.tsx
│
├── guild.db                     SQLite state (created on init)
│
└── workspace/                   Runtime data (created on init)
    ├── memory/
    │   ├── shared/
    │   │   ├── projects/
    │   │   └── conventions/
    │   └── heroes/
    ├── quests/
    │   ├── backlog/
    │   ├── active/
    │   └── done/
    ├── projects/                Per-project config summaries
    ├── inbox/
    ├── outbox/
    └── heroes/                  Per-hero MCP configs
```

---

## Database Schema

### heroes
| Field | Type | Description |
|---|---|---|
| `id` | TEXT PK | Unique identifier |
| `name` | TEXT | Hero name |
| `class` | TEXT | Hero class |
| `status` | TEXT | `idle` \| `on_quest` \| `resting` \| `offline` |
| `level` | INT | Current level |
| `xp` | INT | Experience points |
| `current_quest_id` | TEXT? | Active quest |
| `session_pid` | INT? | Running process ID |
| `last_active` | DATETIME | Last activity |

### projects
| Field | Type | Description |
|---|---|---|
| `id` | TEXT PK | Unique identifier |
| `name` | TEXT UNIQUE | Short name e.g. "greentic" |
| `display_name` | TEXT | Full name |
| `path` | TEXT | Absolute local path |
| `repo_url` | TEXT? | Remote URL |
| `repo_provider` | TEXT? | `github` \| `gitlab` \| `none` |
| `main_branch` | TEXT | Default: `main` |
| `dev_branch` | TEXT | Default: `development` |
| `language` | TEXT? | Primary language |
| `status` | TEXT | `active` \| `paused` \| `archived` |
| `default_mcps` | JSON | Default MCP IDs |
| `created_at` | DATETIME | — |
| `last_active` | DATETIME? | — |

### project_groups
| Field | Type | Description |
|---|---|---|
| `id` | TEXT PK | Group identifier |
| `name` | TEXT UNIQUE | Group name |
| `created_at` | DATETIME | — |

### project_group_members
| Field | Type | Description |
|---|---|---|
| `group_id` | TEXT | FK → project_groups |
| `project_id` | TEXT | FK → projects |

### quest_chains
| Field | Type | Description |
|---|---|---|
| `id` | TEXT PK | Chain ID e.g. GLC-015 |
| `goal` | TEXT | Original developer goal |
| `project_id` | TEXT | Target project |
| `status` | TEXT | `active` \| `done` \| `blocked` |
| `created_at` | DATETIME | — |
| `completed_at` | DATETIME? | — |

### quests
| Field | Type | Description |
|---|---|---|
| `id` | TEXT PK | Quest ID e.g. GLD-042 |
| `chain_id` | TEXT | Parent chain |
| `parent_quest_id` | TEXT? | Dependency |
| `title` | TEXT | Quest title |
| `description` | TEXT | Objective |
| `tier` | TEXT | `COMMON` \| `RARE` \| `EPIC` \| `LEGENDARY` \| `BOSS` |
| `type` | TEXT | `impl` \| `test` \| `review` \| `merge` \| `chore` |
| `status` | TEXT | `backlog` \| `active` \| `blocked` \| `done` |
| `project_id` | TEXT | Target project |
| `branch` | TEXT | Git branch name |
| `req_skills` | JSON | Required skills |
| `assigned_to` | TEXT? | Hero ID |
| `result` | TEXT? | Completion summary |
| `created_at` | DATETIME | — |
| `completed_at` | DATETIME? | — |

### hero_skills
| Field | Type | Description |
|---|---|---|
| `id` | TEXT PK | — |
| `hero_id` | TEXT | FK → heroes |
| `name` | TEXT | Skill name |
| `type` | TEXT | `base` \| `learned` \| `manual` |
| `proficiency` | INT | 1–5 |
| `source` | TEXT? | Quest ID or "manual" |
| `created_at` | DATETIME | — |
| `updated_at` | DATETIME | — |

### mcp_servers
| Field | Type | Description |
|---|---|---|
| `id` | TEXT PK | — |
| `name` | TEXT | Identifier |
| `display_name` | TEXT | Human-readable name |
| `url` | TEXT? | URL-type MCP |
| `command` | TEXT? | Process-type MCP |
| `args` | JSON? | Command args |
| `env_vars` | JSON? | Env var references |
| `skills_served` | JSON | Skills this MCP enables |
| `status` | TEXT | `active` \| `disabled` |
| `added_at` | DATETIME | — |

### hero_mcps
| Field | Type | Description |
|---|---|---|
| `hero_id` | TEXT | FK → heroes |
| `mcp_id` | TEXT | FK → mcp_servers |
| `auto_attach` | BOOLEAN | Always include? |
| `added_at` | DATETIME | — |

### file_locks
| Field | Type | Description |
|---|---|---|
| `file_path` | TEXT PK | Absolute file path |
| `quest_id` | TEXT | Holding quest |
| `hero_id` | TEXT | Holding hero |
| `locked_at` | DATETIME | — |

### memories
| Field | Type | Description |
|---|---|---|
| `id` | TEXT PK | — |
| `owner` | TEXT | `shared` \| hero_id |
| `project_id` | TEXT? | Scope |
| `category` | TEXT | `decision` \| `convention` \| `learning` \| `context` |
| `content` | TEXT | Markdown content |
| `tags` | JSON | Tag array |
| `created_by` | TEXT | Hero ID |
| `updated_at` | DATETIME | — |

### activity_log
| Field | Type | Description |
|---|---|---|
| `id` | TEXT PK | — |
| `timestamp` | DATETIME | — |
| `actor` | TEXT | `guild-master` \| hero_id \| `system` |
| `action` | TEXT | What was done |
| `quest_id` | TEXT? | Related quest |
| `project_id` | TEXT? | Related project |
| `level` | TEXT | `info` \| `warning` \| `critical` \| `fatal` |
