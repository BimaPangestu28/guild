# 12 — CLI Interface

All Guild operations are accessible via the `guild` CLI. The binary is self-contained — no external runtime required.

---

## Setup & Init

```bash
guild init                                    Initialize guild in current directory
guild init --project ./my-repo               Register existing project during init
guild setup telegram                          Configure Telegram bot
guild setup github                            Configure GitHub integration
guild config                                  View all configuration
guild config --set daily-briefing-time 08:00  Update config value
guild config --set cost-cap-daily 10.00
guild config telegram                         Adjust Telegram notification levels
guild config --skip-rookie                    Disable rookie mode guardrails
```

---

## Daily Use

```bash
guild goal "Refactor WASM adapters in greentic"
guild goal --project map-group "Add daily sales report endpoint"
guild status                                  Full overview
guild report                                  Latest Guild Master analysis
guild log                                     Recent activity log
guild cost                                    Today's token usage
```

---

## Project Management

```bash
guild project add                             Interactive registration wizard
guild project add --path ./repo --name myapp  Non-interactive
guild project list                            All registered projects
guild project show greentic                   Project details
guild project edit greentic                   Edit configuration
guild project pause greentic                  Pause — no new quest assignments
guild project resume greentic                 Resume paused project
guild project archive greentic                Archive — read-only
guild project unarchive greentic
guild project remove greentic                 Remove from guild (keeps local files)
guild project health greentic                 Codebase health report

# Multi-repo groups
guild project group create "MAP Group Platform"
guild project group add "MAP Group Platform" ./map-backend
guild project group add "MAP Group Platform" ./map-frontend
guild project group list
guild project group show "MAP Group Platform"

# Per-project MCPs
guild project mcp add greentic databricks-mcp
guild project mcp remove greentic databricks-mcp
guild project mcp list greentic

# Per-project preferred heroes
guild project hero prefer greentic StormForge
guild project hero list greentic
```

---

## Hero Management

```bash
guild recruit                                 Interactive recruitment wizard
guild recruit --class "Rust Sorcerer" --name StormForge
guild heroes                                  Roster overview
guild hero StormForge                         Hero detail + session command
guild hero StormForge --start                 Launch hero session (copy to new terminal)
guild retire StormForge                       Remove hero from roster
guild pause StormForge                        Pause this hero's session
guild resume StormForge                       Resume this hero's session
guild pause --all
guild resume --all
```

---

## Quest Management

```bash
guild quests                                  Full quest board
guild quests --project greentic               Filtered by project
guild quests --status backlog                 Filtered by status
guild quest GLD-042                           Quest detail
guild quest add                               Post quest manually (interactive)
guild assign GLD-042 StormForge               Manual assignment override
guild complete GLD-042                        Mark quest done manually
guild cancel GLD-042                          Cancel quest
```

---

## Skill Management

```bash
guild skill list StormForge                   All skills for a hero
guild skill show StormForge greentic-codebase Skill detail
guild skill add StormForge "map-group-conventions"
guild skill remove StormForge "old-skill"
guild skill edit StormForge greentic-codebase Opens in $EDITOR
guild skill transfer StormForge IronWeave greentic-codebase
```

---

## MCP Management

```bash
guild mcp list                                All registered MCPs
guild mcp status                              Which heroes have which MCPs
guild mcp add --name "my-mcp" --url "..."     Register custom MCP
guild mcp remove my-mcp
guild mcp attach StormForge github-mcp --auto Attach to hero permanently
guild mcp detach StormForge github-mcp
guild mcp attach --project greentic databricks-mcp
guild mcp detach --project greentic databricks-mcp
```

---

## Memory Management

```bash
guild memory                                  Shared memory index
guild memory --project greentic               Project-specific memory
guild memory --hero StormForge                Hero private memory
guild memory --project greentic --adr 001     View specific ADR
guild memory edit --project greentic          Edit in $EDITOR
guild memory edit --hero StormForge --file notes
guild memory clear --hero StormForge --private  Clear private memory
guild memory export --output ./backup.tar.gz  Export all memory
guild memory import ./backup.tar.gz           Import memory
```

---

## Secrets

```bash
guild secret add GITHUB_TOKEN ghp_xxxx
guild secret list                             Names only, never values
guild secret remove GITHUB_TOKEN
```

---

## Dashboard

```bash
guild dashboard                               Open local web UI (localhost:7432)
```
