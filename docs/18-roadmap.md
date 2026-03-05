# 18 — Build Roadmap

---

## Phase 1 — Foundation *(Weeks 1–2)*

- Rust CLI skeleton: `guild init`, `guild status`, `guild goal`
- SQLite schema — all tables from Section 13
- Filesystem structure — workspace, memory, inbox, outbox, projects
- Basic Guild Master loop — filesystem polling, inbox/outbox pattern
- Project registration: `guild project add`, basic config
- Manual hero trigger — session command generated, developer runs it

> **Deliverable:** `guild goal` breaks a goal into quests, writes to hero inboxes. Heroes triggered manually but have injected context. Project registration works. Memory system functional.

---

## Phase 2 — Memory & Skills *(Week 3)*

- Shared and private memory read/write
- Dynamic CLAUDE.md generation and injection
- Hero memory update protocol
- Skill system — base skills, manual skill add, proficiency tracking
- Skill backing files per hero
- Shared project memory accumulation across sessions

> **Deliverable:** Heroes have persistent context. Knowledge accumulates between sessions. Skills visible in `guild hero {name}`.

---

## Phase 3 — Autonomous Trigger *(Weeks 4–5)*

- Claude Code SDK integration in Python agent runtime
- Rust process manager — spawn, monitor, kill hero sessions
- Guild Master fully autonomous loop — no manual hero trigger
- Auto-skill learning on quest completion
- Cost tracking per hero, quest, project
- Circuit breaker — detect and handle stuck or looping heroes

> **Deliverable:** `guild goal` triggers everything automatically. No manual steps until Guild Master escalates.

---

## Phase 4 — Git Workflow *(Week 6)*

- Automated branch creation on quest start
- PR creation and management via GitHub/GitLab API
- Quest chain enforcement — auto-spawn test and review quests
- Branch protection rule setup on `guild project add`
- Multi-repo project groups and cross-repo quest chains

> **Deliverable:** Full git lifecycle automated end-to-end. Branch creation to PR merge without manual steps.

---

## Phase 5 — MCP + Proactive + Notifications *(Week 7)*

- MCP registry and per-session config assembly
- MCP auto-attach logic (built-in + project + quest-based)
- Secrets management (encrypted local store)
- Telegram bot integration and setup wizard
- Daily briefing, blocker escalation, chain completion notifications
- Proactive idle hero assignment
- Weekly codebase health scan and auto-quest creation

> **Deliverable:** Heroes equipped with appropriate tools per quest. Developer gets Telegram updates without polling CLI.

---

## Phase 6 — Dashboard + Launch *(Week 8)*

- React local dashboard bundled into binary
- Real-time hero status, quest board, memory viewer, activity log
- Project management UI (register, pause, archive via dashboard)
- License system implementation
- Onboarding wizard polish
- Documentation, README, launch assets

> **Launch target:** Show HN — *"I built a self-hosted multi-agent system that remembers your codebase."*
