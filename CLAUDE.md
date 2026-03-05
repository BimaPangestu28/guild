# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Guild is a self-hosted multi-agent development OS for solo developers. It orchestrates multiple Claude Code agent sessions ("heroes") coordinated by an autonomous "Guild Master" agent. Heroes have persistent memory, specialized skills, and follow a strict quest chain workflow (implement -> test -> review -> merge).

**Status:** Design/documentation phase. The `docs/` directory contains the full product specification (sections 01-19). No implementation code exists yet.

## Technology Stack

| Layer | Technology |
|---|---|
| Core runtime | Rust (single binary, CLI entrypoint, process management, SQLite) |
| Agent logic | Python (Claude Code SDK, Guild Master brain, hero runtime) |
| Dashboard | React (bundled into binary at build time) |
| State | SQLite (`guild.db`) |
| Memory | Markdown files (human-readable, git-friendly) |

## Planned Repository Structure

```
src/              Rust core (main.rs, process_manager.rs, watcher.rs, ipc.rs, db.rs, secrets.rs)
agents/           Python agent logic (guild_master.py, hero_runtime.py, memory_manager.py, mcp_builder.py)
dashboard/        React local web UI (GuildHall, QuestBoard, HeroRoster, MemoryViewer)
workspace/        Runtime data (memory/, quests/, projects/, inbox/, outbox/, heroes/)
guild.db          SQLite state
```

## Key Architecture Concepts

- **Guild Master** is an autonomous orchestrator agent (not a chatbot). It decomposes goals into quest chains, assigns quests to heroes, and manages git lifecycle. Decision framework: reversible actions are autonomous, irreversible actions escalate to developer.
- **Heroes** are specialized Claude Code sessions with persistent identity, class-based skills, and injected `CLAUDE.md` context. No hero may hold two roles in the same quest chain.
- **Quest chains** follow: implementation -> test (different hero) -> review (third hero) -> merge (Guild Master). Branches always cut from `development`, PRs target `development`, merges to `main` require human approval.
- **Memory system** has shared (project knowledge, ADRs, conventions) and private (per-hero CLAUDE.md, history, notes, skills) layers. Memory files are dynamically assembled and injected at session start.
- **Communication** uses filesystem inbox/outbox pattern for hero<->Guild Master coordination, plus Telegram for developer notifications.

## Build Roadmap Phases

Phase 1 (Foundation): Rust CLI skeleton, SQLite schema, filesystem structure, basic Guild Master loop, project registration
Phase 2 (Memory & Skills): Shared/private memory, CLAUDE.md injection, skill system
Phase 3 (Autonomous Trigger): Claude Code SDK integration, process manager, auto-skill learning, cost tracking
Phase 4 (Git Workflow): Branch/PR automation, quest chain enforcement, multi-repo groups
Phase 5 (MCP + Notifications): MCP registry, secrets, Telegram bot, proactive behaviors
Phase 6 (Dashboard + Launch): React dashboard, onboarding wizard, license system

## Design Documentation

All design specs are in `docs/` numbered 01-19. Key references:
- `docs/13-architecture.md` — full DB schema, repo structure, tech stack
- `docs/12-cli.md` — complete CLI command reference
- `docs/06-guild-master.md` — Guild Master system prompt, decision framework, behaviors
- `docs/05-memory-system.md` — memory architecture, CLAUDE.md injection template
- `docs/04-git-workflow.md` — branch strategy, commit conventions, PR templates
- `docs/02-core-concepts.md` — guild, heroes, quests, quest chains
- `docs/08-skill-system.md` — hero skill types, proficiency, auto-learning

## Conventions

- Commit format: `[GLD-{id}] {short description} - {hero_name}`
- Branch naming: `feature/GLD-*`, `fix/GLD-*`, `chore/GLD-*`
- Git branches always from `development`, never from `main`
- PRs always target `development`; `development` -> `main` requires human approval
- Targets macOS and Linux only (no Windows support in v1)
