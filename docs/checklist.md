# Guild — Build Checklist

---

## Phase 0 — Dashboard UI (Done)

### 0.1 React Dashboard + Pixel Art
- [x] Setup React + Vite project di `dashboard/`
- [x] Copy pixel art assets dari CraftPix guild hall pack
- [x] Pre-render TMX tilemap ke PNG (interior + exterior)
- [x] Sprite slicing pipeline (`scripts/slice-sprites.mjs`)
- [x] AnimatedSprite component (CSS sprite animation)
- [x] GuildScene — full game-like guild hall view with tilemap background
- [x] HUD overlay (top stats bar, bottom nav)
- [x] Game-style panels: HeroPanel, QuestPanel, ProjectPanel, MemoryPanel, LogPanel
- [x] Mock data layer (`dashboard/src/data/mock.ts`)

---

## Phase 1 — Foundation (Done)

### 1.1 Rust Project Setup
- [x] `cargo init` — setup Rust project dengan binary target
- [x] Setup Cargo.toml dependencies: `clap`, `rusqlite`, `serde`/`serde_json`, `uuid`, `chrono`, `colored`, `dialoguer`
- [x] Setup `src/main.rs` sebagai CLI entrypoint dengan clap subcommands
- [x] Buat module structure: `db.rs`, `cli/mod.rs`, `cli/init.rs`, etc.
- [x] Test build di Linux (WSL2)

### 1.2 SQLite Schema & Database Layer (`src/db.rs`)
- [x] Create `guild.db` on `guild init`
- [x] Table: `heroes` (id, name, class, status, level, xp, current_quest_id, session_pid, last_active)
- [x] Table: `projects` (id, name, display_name, path, repo_url, repo_provider, main_branch, dev_branch, language, status, default_mcps, created_at, last_active)
- [x] Table: `project_groups` (id, name, created_at)
- [x] Table: `project_group_members` (group_id, project_id)
- [x] Table: `quest_chains` (id, goal, project_id, status, created_at, completed_at)
- [x] Table: `quests` (id, chain_id, parent_quest_id, title, description, tier, type, status, project_id, branch, req_skills, assigned_to, result, created_at, completed_at)
- [x] Table: `hero_skills` (id, hero_id, name, type, proficiency, source, created_at, updated_at)
- [x] Table: `mcp_servers` (id, name, display_name, url, command, args, env_vars, skills_served, status, added_at)
- [x] Table: `hero_mcps` (hero_id, mcp_id, auto_attach, added_at)
- [x] Table: `file_locks` (file_path, quest_id, hero_id, locked_at)
- [x] Table: `memories` (id, owner, project_id, category, content, tags, created_by, updated_at)
- [x] Table: `activity_log` (id, timestamp, actor, action, quest_id, project_id, level)
- [x] `log_activity()` helper function
- [ ] CRUD functions untuk setiap table
- [x] Hourly auto-backup logic (`~/.guild/backups/guild-{timestamp}.db`, retain 24)

### 1.3 Filesystem Structure
- [x] `guild init` creates `~/.guild/` root directory
- [x] Create `workspace/memory/shared/projects/`
- [x] Create `workspace/memory/shared/conventions/`
- [x] Create `workspace/memory/heroes/`
- [x] Create `workspace/quests/backlog/`, `workspace/quests/active/`, `workspace/quests/done/`
- [x] Create `workspace/projects/`
- [x] Create `workspace/inbox/`
- [x] Create `workspace/outbox/`
- [x] Create `workspace/heroes/`
- [x] Write default shared memory templates (conventions: `git.md`, `code-style.md`, `testing.md`)

### 1.4 CLI — `guild init`
- [x] System requirements check: git 2.x, Python 3.11+
- [x] Prompt Anthropic API key, validate via API call
- [x] Store API key securely (encrypted local store)
- [x] Create directory structure (1.3)
- [x] Initialize SQLite database (1.2)
- [x] Optional: Telegram setup prompt (store token + chat ID)
- [x] Optional: License key prompt (Free tier default)
- [x] Optional: Recruit first hero (interactive class selection, name input)
- [x] Optional: Register first project (`guild project add` flow)
- [x] Print summary dan next steps

### 1.5 CLI — `guild project add`
- [x] Flag mode: `--path`, `--name`, `--provider`, `--main`, `--dev`
- [x] Interactive mode (wizard) kalau tanpa flags
- [x] Validate path exists dan is a git repo
- [x] Detect primary language dari file extensions
- [x] Read existing conventions (.editorconfig, .eslintrc, etc.) ke shared memory
- [x] Check `dev_branch` exists — create from main kalau belum ada
- [x] Create shared memory template: `workspace/memory/shared/projects/{name}.md`
- [x] Create ADR folder: `workspace/memory/shared/projects/{name}-adr/`
- [x] Create project config summary: `workspace/projects/{name}/config.md`
- [x] Insert project record ke `guild.db`
- [ ] Scan TODOs/open issues — offer to create quests (optional)

### 1.6 CLI — `guild project` Subcommands
- [x] `guild project list` — list semua registered projects
- [x] `guild project show {name}` — detail project + config
- [x] `guild project edit {name}` — interactive edit
- [x] `guild project pause {name}` — set status=paused, block new quests
- [x] `guild project resume {name}` — set status=active
- [x] `guild project archive {name}` — set status=archived, block active quests
- [x] `guild project unarchive {name}`
- [x] `guild project remove {name}` — confirm dialog, delete from db (keep local files)
- [x] `guild project health {name}` — placeholder

### 1.7 CLI — `guild recruit` (Hero Creation)
- [x] Interactive wizard: pilih class (7 options), input name
- [x] Flag mode: `--class "Rust Sorcerer" --name StormForge`
- [x] Insert hero record ke db (status=offline, level=1, xp=0)
- [x] Create hero memory directory: `workspace/memory/heroes/{name}/`
- [x] Create `CLAUDE.md`, `history.md`, `notes.md`, `skills/` di hero dir
- [x] Insert base skills ke `hero_skills` table berdasarkan class
- [x] Print session start command: `guild hero {name} --start`

### 1.8 CLI — `guild heroes` & Hero Management
- [x] `guild heroes` — roster overview (name, class, status, level, current quest)
- [x] `guild hero {name}` — hero detail + skills
- [x] `guild hero {name} --start` — assemble CLAUDE.md + generate session command
- [x] `guild retire {name}` — remove hero dari roster (confirm dialog)
- [x] `guild pause {name}` — pause hero session
- [x] `guild resume {name}` — resume hero session

### 1.9 CLI — `guild goal`
- [x] Accept goal string: `guild goal "description"`
- [x] Accept `--project {name}` flag untuk scoping
- [x] Write goal ke `workspace/inbox/guild-master.md`
- [x] Trigger Guild Master cycle (or print message kalau GM belum running)

### 1.10 CLI — `guild status`, `guild log`, `guild report`
- [x] `guild status` — full overview: heroes, active quests, backlog count, projects
- [x] `guild log` — recent activity_log entries dari db
- [x] `guild report` — latest Guild Master output dari `workspace/outbox/guild-master.md`
- [x] `guild cost` — placeholder

### 1.11 CLI — Quest Management
- [x] `guild quests` — full quest board
- [x] `guild quests --project {name}` — filter by project
- [x] `guild quests --status {status}` — filter by status
- [x] `guild quest show {id}` — quest detail
- [x] `guild quest add` — placeholder (manual quest creation)
- [x] `guild assign {quest_id} {hero_name}` — manual assignment override
- [x] `guild quest complete {quest_id}` — mark done manually
- [x] `guild quest cancel {quest_id}` — cancel quest

### 1.12 Basic Guild Master Loop (Python)
- [x] Setup `agents/` Python directory dengan requirements
- [x] `agents/guild_master.py` — main orchestrator brain
- [x] Filesystem polling: watch `workspace/inbox/guild-master.md` untuk new goals
- [x] Filesystem polling: watch `workspace/outbox/*.md` untuk hero completion reports
- [x] Goal decomposition: parse goal → create quest chain + quests di db (via Claude API)
- [x] Quest assignment: match quest req_skills ke hero skills
- [x] Write quest brief ke `workspace/inbox/{hero_name}.md`
- [x] Structured output ke `workspace/outbox/guild-master.md` (ANALYSIS, ACTIONS, ESCALATIONS, NEXT)
- [x] Activity logging ke db untuk setiap action
- [x] XP reward + level-up on quest completion
- [x] Enforce: Boss tier must be decomposed, never assigned directly
- [x] Enforce: max 4h estimated work per quest

### 1.13 Manual Hero Trigger
- [x] `guild hero {name} --start` generates Claude Code session command
- [x] Command includes path ke assembled `CLAUDE.md`
- [x] Command printed ke terminal
- [x] Copied to clipboard
- [x] Hero picks up quest dari `workspace/inbox/{name}.md`

---

## Phase 2 — Memory & Skills (Week 3)

### 2.1 Memory Manager (`agents/memory_manager.py`)
- [x] Read shared memory: `workspace/memory/shared/projects/{name}.md`
- [x] Read hero private memory: `workspace/memory/heroes/{name}/notes.md`
- [x] Read hero history: `workspace/memory/heroes/{name}/history.md`
- [x] Read hero skills: `workspace/memory/heroes/{name}/skills/{skill}.md`
- [x] Write ke semua memory locations
- [x] Memory file size check — warn kalau approaching 50KB

### 2.2 Dynamic CLAUDE.md Generation
- [x] Assemble dari 4 sources: hero identity, quest context, personal context, project context
- [x] Hero identity section: class, skills, focus area, guild rules
- [x] Current quest section: ID, objective, branch, project, chain role
- [x] Personal context: notes.md
- [x] Project context: shared/projects/{project}.md relevant section
- [x] Skill context: relevant skill backing files matching project
- [x] Memory update protocol instructions (outbox format, what goes where)
- [x] Guild rules (commit format, branch rules, never push to main)
- [x] Write assembled CLAUDE.md ke `workspace/memory/heroes/{name}/CLAUDE.md`

### 2.3 Hero Memory Update Protocol
- [x] Hero writes outbox format: status, summary, files_changed, learnings, blockers
- [x] Guild Master reads outbox → processes learnings
- [x] Route learnings: architectural → ADR, project-wide → shared memory, personal → notes.md
- [x] Update hero history.md dengan quest completion entry
- [x] Clear current quest section dari hero CLAUDE.md

### 2.4 Shared Memory Accumulation
- [x] Guild Master checks hero outbox learnings field
- [x] Append project-relevant learnings ke `shared/projects/{project}.md`
- [x] Detect conflicts dengan existing shared memory (Section 10 Scenario C)
- [x] Create ADR untuk architectural decisions (`shared/projects/{name}-adr/adr-NNN.md`)
- [x] No duplicate information — check before writing

### 2.5 Auto-Summarization
- [x] Detect memory file > 50KB
- [x] Archive current content ke `workspace/memory/heroes/{name}/archive/{date}-notes.md`
- [x] Summarize ke condensed version
- [x] Log summarization event

### 2.6 Skill System
- [x] Base skills defined per hero class (from appendix)
- [x] `guild skill list {hero}` — list all skills
- [x] `guild skill show {hero} {skill}` — skill detail
- [x] `guild skill add {hero} {skill}` — manual skill add (type=manual)
- [x] `guild skill remove {hero} {skill}`
- [x] `guild skill edit {hero} {skill}` — open in $EDITOR
- [x] `guild skill transfer {from_hero} {to_hero} {skill}` — copy skill backing file
- [x] Skill backing files: create `workspace/memory/heroes/{name}/skills/{skill}.md`

### 2.7 Proficiency Tracking
- [x] Track quest count per domain/project per hero
- [x] Auto-update proficiency: 1-2 quests=1, 3-5=2, 6-10=3, 11-20=4, 21+=5
- [x] Update proficiency on quest completion
- [x] At proficiency >= 4: extract key learnings ke shared memory

### 2.8 Memory CLI Commands
- [x] `guild memory show` — shared memory index
- [x] `guild memory show --project {name}` — project-specific memory
- [x] `guild memory show --hero {name}` — hero private memory
- [x] `guild memory show --project {name} --adr {number}` — view specific ADR
- [x] `guild memory edit --project {name}` — edit in $EDITOR
- [x] `guild memory edit --hero {name} --file notes`
- [x] `guild memory clear --hero {name}` — clear private memory
- [x] `guild memory export --output {path}` — export all memory
- [x] `guild memory import {path}` — import memory

---

## Phase 3 — Autonomous Trigger (Weeks 4-5)

### 3.1 Claude Code SDK Integration (`agents/hero_runtime.py`)
- [x] Python wrapper untuk Claude Code CLI
- [x] Start session dengan injected CLAUDE.md
- [x] Pass MCP config path ke session
- [x] Capture session PID
- [x] Monitor session output (stdout/stderr)

### 3.2 Rust Process Manager (`src/process_manager.rs`)
- [x] Spawn hero sessions (Python → Claude Code CLI)
- [x] Store PID di guild.db (`hero.session_pid`)
- [x] Heartbeat check — detect dead PIDs
- [x] SIGTERM untuk `guild pause {name}`
- [x] Re-spawn untuk `guild resume {name}`
- [x] Max 3 restart retries per quest — then mark blocked

### 3.3 Guild Master Autonomous Loop
- [x] Continuous polling loop (configurable interval)
- [x] On goal received → decompose, assign, spawn hero automatically
- [x] On quest completion → spawn next chain quest automatically
- [x] On hero idle → check backlog, auto-assign matching quest
- [x] On hero blocked (1st time) → attempt resolve via shared memory/ADRs
- [x] On hero blocked (2nd time) → decompose quest into smaller units
- [x] On hero blocked (needs credentials/arch decision) → escalate immediately

### 3.4 Quest Chain Automation
- [x] Implementation complete → auto-create test quest (different hero)
- [x] Test pass → auto-create review quest (third hero)
- [x] Review approved → mark chain done
- [ ] Review changes requested → create address-review quest → back to implementor
- [x] Chain rule enforcement: no hero holds two roles in same chain

### 3.5 Session Crash Recovery
- [x] Detect dead PID via heartbeat
- [x] Set hero status=offline, clear session_pid
- [x] Check: recent commits exist? → re-spawn with recovery context block
- [x] Check: no commits? → reset quest to backlog
- [x] Recovery CLAUDE.md block: last known action, last commit, quest status
- [x] Notify developer via Telegram Level 3 kalau quest was active

### 3.6 Rate Limit Handling
- [x] Detect no output > 5 minutes
- [x] If rate limit: hero status=resting, schedule re-activation after cooldown
- [x] If other cause: treat as crash recovery
- [x] Log event

### 3.7 Auto-Skill Learning
- [x] On quest completion: check if project-related skill exists (via proficiency tracking)
- [x] Exists → increment proficiency based on quest count
- [x] Not exists → create new learned skill (proficiency=1)
- [x] Parse outbox for new patterns/gotchas → append ke skill backing file
- [x] At proficiency >= 4 → extract ke shared memory

### 3.8 Cost Tracking
- [x] Track token usage per Guild Master API call
- [x] Track token usage per hero session
- [x] Track token usage per project
- [x] `guild cost` CLI command — today's breakdown (placeholder exists)
- [x] Configurable daily cap: `guild config --set cost-cap-daily {amount}`
- [x] Warning at 80% cap → Telegram notification
- [x] Auto-pause all heroes at 100% cap

### 3.9 Circuit Breaker
- [x] Detect stuck hero: no output + no commits > configurable threshold
- [x] Detect looping hero: same error pattern repeated > 3x
- [x] Max tokens per quest — terminate session kalau exceeded
- [x] Dead-man timer per quest — escalate kalau exceeded
- [x] Kill and restart on stuck detection

---

## Phase 4 — Git Workflow (Week 6)

### 4.1 Automated Branch Management
- [x] On quest creation: generate branch name `{type}/GLD-{id}-{slug}`
- [x] On quest start: create branch from `development` (never from `main`)
- [x] On quest complete + merge: delete merged branch
- [x] Handle: branch already exists → reuse if same quest, append `-v2` if different

### 4.2 PR Automation
- [x] On test quest pass: auto-create PR from feature branch → `development`
- [x] PR body auto-generated: quest description, changed files, learnings
- [x] GitHub API integration via `gh`
- [x] GitLab API integration via `glab`
- [x] Provider=none: notify developer with manual merge command

### 4.3 Quest Chain Enforcement
- [x] After impl complete → auto-spawn test quest (assign different hero) (Phase 3)
- [x] After test pass → create PR → auto-spawn review quest (Phase 3)
- [x] After review approved → mark chain done (Phase 3)
- [x] After review changes requested → create fix quest → assign back to implementor
- [x] Common quests (<1hr, low risk) may skip test/review — log this decision
- [x] Enforce chain rule: no hero holds two roles in same chain (Phase 3)

### 4.4 Branch Protection Setup
- [x] On `guild project add`: configure branch protection rules via provider API
- [x] `main`: no direct push, human approval required
- [x] `development`: no direct push, hero reviewer + tests required
- [ ] Feature/fix/chore branches: heroes push freely, cannot self-merge
- [x] Handle: branch protection setup fails → log warning, remind developer

### 4.5 Development → Main Merge
- [x] Guild Master monitors `development` branch
- [x] When ready: send Telegram merge approval request
- [x] Wait for `/approve {chain_id}` dari developer
- [x] On approve: create PR development → main, merge
- [x] On reject: keep on development, log reason

### 4.6 Multi-Repo Project Groups
- [x] `guild project group create {name}`
- [x] `guild project group add {name} {path}`
- [x] `guild project group list`
- [x] `guild project group show {name}`
- [ ] Cross-repo quest chains: each repo gets own branch/PR, linked under one chain ID
- [x] Shared memory across repos in group

### 4.7 Commit Convention Enforcement
- [x] Heroes follow: `[GLD-{id}] {short description} — {hero_name}` (in CLAUDE.md rules)
- [x] Guild Master validates commit messages dari hero sessions
- [x] WIP commit on pause: `[GLD-{id}] WIP — paused by developer — {hero_name}`

### 4.8 File-Level Locking
- [x] Before quest assignment: parse description, identify likely files
- [x] Check `file_locks` table for conflicts (`db::lock_files`)
- [x] If conflict: queue quest until lock released
- [x] On quest completion/cancel: release all locks (`db::release_locks`)
- [x] Auto-activate queued quests when lock released
- [x] `guild locks` — show active file locks

---

## Phase 5 — MCP + Proactive + Notifications (Week 7)

### 5.1 MCP Registry
- [x] `guild mcp add --name {name} --url {url}` — URL-type MCP
- [x] `guild mcp add --name {name} --command {cmd} --args {args}` — process-type MCP
- [x] `guild mcp remove {name}`
- [x] `guild mcp list` — all registered MCPs
- [x] `guild mcp status` — which heroes have which MCPs
- [x] Skills-served mapping per MCP

### 5.2 MCP Auto-Attach Logic (`agents/mcp_builder.py`)
- [x] Always attach: filesystem, git (built-in)
- [x] Permanent: hero_mcps WHERE auto_attach=true
- [x] Quest-based: MCPs WHERE skills_served overlaps quest.req_skills
- [x] Project default: project.default_mcps
- [x] Generate `workspace/heroes/{name}/mcp-config.json` at session start
- [x] Resolve secrets at generation time (never write plaintext to disk)

### 5.3 MCP Hero/Project Attachment
- [x] `guild mcp attach {hero} {mcp} --auto` — permanent attach ke hero
- [x] `guild mcp detach {hero} {mcp}`
- [x] `guild mcp attach --project {name} {mcp}` — project default
- [x] `guild mcp detach --project {name} {mcp}`
- [x] `guild project mcp add {project} {mcp}` (alias)
- [x] `guild project mcp remove {project} {mcp}` (alias)
- [x] `guild project mcp list {project}` (alias)

### 5.4 MCP Failure Handling
- [x] Required MCP unreachable → check via health check
- [x] Optional MCP unreachable → start without it, log warning
- [x] MCP crash mid-session → hero continues, logs warning, reports in outbox

### 5.5 Secrets Management (`src/cli/secret.rs`)
- [x] `guild secret add {name} {value}` — encrypt dan store
- [x] `guild secret list` — show names only, never values
- [x] `guild secret remove {name}`
- [x] Encryption key derived dari hostname + home directory
- [x] Secrets resolved at MCP config generation time

### 5.6 Telegram Bot Integration
- [x] `guild setup-telegram` — interactive wizard
- [x] Store bot token dan chat ID in config.json
- [x] Polling mode (long polling every 10s) — default
- [ ] Optional webhook mode

### 5.7 Telegram Inbound Commands
- [x] `/status` — hero roster + active quests
- [x] `/report` — latest Guild Master analysis
- [x] `/heroes` — roster with status/level
- [x] `/quests` — quest board
- [x] `/pause` — pause all heroes
- [x] `/resume` — resume all heroes
- [x] `/approve {chain_id}` — approve dev→main merge
- [x] `/reject {chain_id}` — reject merge
- [x] `/goal {text}` — post new goal
- [x] `/cost` — today's usage breakdown
- [x] `/help` — list commands
- [ ] Natural language parsing (non-prefixed messages)
- [ ] Ambiguous input (confidence <60%) → ask clarification, don't execute

### 5.8 Telegram Outbound Notifications
- [x] Level 1 (Silent): log only — routine assignments, minor decisions
- [x] Level 2 (Dashboard): quest completions, hero level-ups, stored in notifications JSONL
- [x] Level 3 (Telegram message): blockers, daily briefing, anomalies
- [x] Level 4 (Telegram urgent): critical failures, cost overrun, requires decision
- [x] Quest completion format
- [x] Merge approval request format
- [x] Cost warning format
- [x] Escalation format (problem, options, A/B choice)
- [x] Conversation context: store last 10 messages, clear daily

### 5.9 Telegram Daily Briefing
- [x] Configurable time: `guild config --set daily-briefing-time {HH:MM}`
- [x] Content: active quests, hero availability, priorities, blockers
- [x] Max 200 words

### 5.10 Proactive Behaviors
- [x] Idle hero check: hero → idle → check backlog → auto-assign if match (Phase 3)
- [x] On code push: test coverage delta, lint errors, TODO additions
- [x] Weekly codebase health scan per active project
- [x] Auto-create chore quests above threshold (outdated deps, coverage drop, etc.)
- [x] PR idle > 24h: re-ping reviewer or reassign

### 5.11 Notification Level Configuration
- [x] `guild setup-telegram` — adjust notification levels
- [x] Per-event level customization
- [x] Telegram API unreachable → queue notifications, retry every 5 min
- [x] Bot token invalid → disable Telegram, fallback to dashboard-only

---

## Phase 6 — Dashboard Integration + Launch (Week 8)

### 6.1 Dashboard API Layer
- [x] Setup React project di `dashboard/`
- [x] Bundle into Rust binary at build time (no Node.js required on user machine)
- [x] `guild dashboard` → serve di localhost:7432
- [x] API layer: Rust serves JSON endpoints dari guild.db (tiny_http)
- [x] Replace mock data with real API calls (usePolling hook)
- [x] API endpoints: /api/status, /api/heroes, /api/quests, /api/projects, /api/log, /api/locks, /api/mcps
- [x] Static file serving with SPA fallback
- [x] CORS headers on all API responses

### 6.2 Dashboard Components
- [x] `GuildScene.tsx` — main game-like guild hall view with animated sprites
- [x] `QuestPanel.tsx` — quest list panel
- [x] `HeroPanel.tsx` — hero roster panel with status/level/skills
- [x] `MemoryPanel.tsx` — memory browser panel
- [x] `LogPanel.tsx` — activity log panel
- [x] `ProjectPanel.tsx` — project panel
- [x] Wire all panels to real API data (with mock fallback)

### 6.3 Real-Time Updates
- [x] Polling (5s interval) untuk live hero status, quests, projects, log
- [x] Quest status changes reflected via polling
- [x] Activity log auto-refresh
- [x] Queued Telegram notifications visible in dashboard

### 6.4 License System
- [x] Offline license key verification algorithm
- [x] Free tier: 2 heroes max
- [x] Pro tier: 8 heroes, full features
- [x] License stored locally, works offline after activation (`~/.guild/license.key`)
- [x] Enforce limits at hero creation (`license.check_hero_limit()`)
- [x] `guild activate {key}` command

### 6.5 Onboarding Polish
- [x] Rookie mode flag in config.json (set on first init)
- [x] "Why I did this" explanations on every autonomous action during rookie
- [x] Getting started tips printed on first init
- [x] `guild config skip-rookie` to disable
- [x] `guild config show/set` for all configuration
- [x] `guild doctor` health check command

### 6.6 Documentation & Launch
- [x] README.md — project overview, installation, quickstart, CLI reference
- [x] Contributing guide (if open source)
- [ ] Show HN post draft
- [ ] Launch assets (screenshots, demo GIF)

---

## Cross-Cutting (All Phases)

### Error Handling
- [x] FATAL: guild stops entirely, manual intervention required
- [x] CRITICAL: affected component pauses, Telegram Level 4 notification
- [x] WARNING: guild continues, logged, included in daily report
- [x] INFO: guild continues, logged only
- [x] Guild Master crash → auto-restart after 30s, re-read state from db
- [x] Guild Master stuck >10 min → kill and restart
- [x] guild.db corruption → stop, notify, restore from hourly backup
- [x] Hero modifies file outside project scope → revert via git, suspend hero
- [x] Hero attempts push to main → block (branch protection), suspend, notify

### Testing
- [x] Rust unit tests untuk db layer, process manager, CLI parsing
- [x] Python unit tests untuk guild_master, memory_manager, mcp_builder
- [x] Integration tests: goal → quest chain → hero assignment flow
- [ ] Test on both macOS dan Linux dari Phase 1

### Backup & Recovery
- [x] `guild.db` backup on demand (`guild backup create`)
- [x] Retain last 24 backups
- [x] `guild backup list`
- [x] `guild backup restore {filename}` (with safety backup + confirm prompt)
- [x] Auto-backup every hour
