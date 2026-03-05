# Guild

**Self-hosted multi-agent development OS -- orchestrate Claude Code agents like an RPG guild.**

---

## What is Guild?

Guild turns a solo developer into a full development team by orchestrating multiple Claude Code agent sessions. Each agent is a "hero" with a class, specialized skills, and an XP/leveling system. A Guild Master AI decomposes high-level goals into quest chains and assigns them to heroes automatically. The entire system runs locally, backed by SQLite, and is presented through a game-inspired pixel art dashboard.

---

## Features

- **Hero system** -- 7 character classes, class-based skills, XP and leveling
- **Quest chains** -- structured workflow: implement, test, review, merge (each phase assigned to a different hero)
- **Guild Master AI orchestrator** -- autonomous goal decomposition, quest assignment, and blockers resolution
- **Memory system** -- shared and private memory layers, ADRs, auto-summarization when files grow large
- **Git workflow automation** -- branch creation, commit conventions, PR creation via `gh` (GitHub) or `glab` (GitLab)
- **MCP server management** -- register, auto-attach, and configure MCP servers per hero and project
- **Telegram bot notifications** -- inbound commands (`/status`, `/goal`, `/approve`) and tiered outbound alerts
- **Game-style pixel art dashboard** -- real-time guild hall view with animated sprites, quest board, hero roster
- **Fully local** -- SQLite-based, no cloud dependency, runs entirely on your machine

---

## Quick Start

```bash
# Prerequisites: Rust, Python 3.11+, Node.js (for dashboard build)

git clone https://github.com/BimaPangestu28/guild.git
cd guild
cargo build --release

# Initialize
./target/release/guild init

# Register a project
guild project add --path /your/project --name myapp

# Recruit your first hero
guild recruit --class "Rust Sorcerer" --name StormForge

# Post a goal
guild goal "Add user authentication" --project myapp

# Start Guild Master (needs ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-ant-...
python3 agents/guild_master.py

# Start hero session
guild hero StormForge --start

# Open dashboard
guild dashboard
```

---

## CLI Reference

### Core

| Command | Description |
|---------|-------------|
| `guild init` | Initialize Guild (creates `~/.guild/`, database, workspace) |
| `guild status` | Overview of heroes, active quests, backlog, projects |
| `guild log` | Recent activity log entries |
| `guild report` | Latest Guild Master analysis output |
| `guild cost` | Usage/cost breakdown |
| `guild dashboard` | Launch pixel art web dashboard on localhost:7432 |

### Goals and Quests

| Command | Description |
|---------|-------------|
| `guild goal "description" --project name` | Post a new goal for the Guild Master |
| `guild quests` | Show the quest board |
| `guild quests --project name` | Filter quests by project |
| `guild quests --status status` | Filter quests by status |
| `guild quest show {id}` | Quest detail view |
| `guild quest add` | Manually create a quest |
| `guild quest complete {id}` | Mark a quest done manually |
| `guild quest cancel {id}` | Cancel a quest |
| `guild assign {quest_id} {hero}` | Manually assign a quest to a hero |
| `guild locks` | Show active file locks |

### Heroes

| Command | Description |
|---------|-------------|
| `guild recruit` | Recruit a new hero (interactive or `--class` / `--name` flags) |
| `guild heroes` | Roster overview (name, class, status, level, current quest) |
| `guild hero {name}` | Hero detail and skills |
| `guild hero {name} --start` | Assemble CLAUDE.md and start hero session |
| `guild retire {name}` | Remove hero from roster |
| `guild pause {name}` | Pause a hero session |
| `guild resume {name}` | Resume a hero session |

### Projects

| Command | Description |
|---------|-------------|
| `guild project add` | Register a project (interactive or with flags) |
| `guild project list` | List all registered projects |
| `guild project show {name}` | Project detail |
| `guild project pause {name}` | Pause a project |
| `guild project resume {name}` | Resume a project |
| `guild project archive {name}` | Archive a project |
| `guild project unarchive {name}` | Unarchive a project |
| `guild project remove {name}` | Remove a project from Guild |
| `guild project health {name}` | Project health check |

### Skills

| Command | Description |
|---------|-------------|
| `guild skill list {hero}` | List hero skills |
| `guild skill show {hero} {skill}` | Skill detail |
| `guild skill add {hero} {skill}` | Add a skill manually |
| `guild skill remove {hero} {skill}` | Remove a skill |
| `guild skill transfer {from} {to} {skill}` | Copy a skill between heroes |

### Memory

| Command | Description |
|---------|-------------|
| `guild memory show` | Shared memory index |
| `guild memory show --project {name}` | Project-specific memory |
| `guild memory show --hero {name}` | Hero private memory |
| `guild memory show --project {name} --adr {n}` | View a specific ADR |
| `guild memory edit --project {name}` | Edit project memory in $EDITOR |
| `guild memory edit --hero {name} --file notes` | Edit hero notes |
| `guild memory clear --hero {name}` | Clear hero private memory |
| `guild memory export --output {path}` | Export all memory |
| `guild memory import {path}` | Import memory |

### MCP Servers

| Command | Description |
|---------|-------------|
| `guild mcp add --name {n} --url {url}` | Register a URL-type MCP server |
| `guild mcp add --name {n} --command {cmd}` | Register a process-type MCP server |
| `guild mcp remove {name}` | Remove an MCP server |
| `guild mcp list` | List all registered MCP servers |
| `guild mcp status` | Show hero-MCP attachments |
| `guild mcp attach {hero} {mcp}` | Attach MCP to hero (`--auto` for permanent) |
| `guild mcp detach {hero} {mcp}` | Detach MCP from hero |

### Secrets and Notifications

| Command | Description |
|---------|-------------|
| `guild secret add {name} {value}` | Store an encrypted secret |
| `guild secret list` | List secret names |
| `guild secret remove {name}` | Remove a secret |
| `guild setup-telegram` | Configure Telegram bot integration |

---

## Architecture

Guild is composed of three layers:

- **Rust binary** -- CLI entrypoint, HTTP API (serves dashboard and JSON endpoints), SQLite database access, process management for hero sessions.
- **Python agents** -- Guild Master orchestrator (`agents/guild_master.py`), hero runtime (`agents/hero_runtime.py`), memory manager (`agents/memory_manager.py`), MCP config builder (`agents/mcp_builder.py`).
- **React dashboard** -- game-style pixel art UI with animated sprites, real-time polling against the Rust HTTP API. Located in `dashboard/`.

All state lives in a single SQLite database (`guild.db`). Memory is stored as Markdown files under `workspace/memory/` for human readability and git-friendliness.

---

## Credits

See [CREDITS.md](CREDITS.md) for full attribution. Pixel art assets by [CraftPix.net](https://craftpix.net/).

---

## License

MIT
