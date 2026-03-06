# Show HN: Guild -- Self-hosted multi-agent dev OS for solo developers

## Title
Show HN: Guild -- Open-source multi-agent development OS that orchestrates Claude Code sessions

## Post

Hey HN,

I built Guild, a self-hosted system that lets solo developers run multiple AI coding agents simultaneously, coordinated by an autonomous "Guild Master" orchestrator.

**The problem:** As a solo dev, I wanted to use AI coding agents for parallel work -- one agent implementing a feature, another writing tests, a third reviewing code. But managing multiple Claude Code sessions manually is chaos. No coordination, no memory, no workflow.

**What Guild does:**

- **Guild Master** -- An autonomous orchestrator that decomposes goals into quest chains (implement -> test -> review -> merge), assigns them to specialized "hero" agents, and manages the full git lifecycle
- **Heroes** -- Specialized Claude Code sessions with persistent identity, skills, and memory. A "Rust Sorcerer" handles systems work while a "TypeScript Templar" handles frontend
- **Quest chains** -- Enforced workflow: different heroes implement, test, and review each piece of work. No hero can hold two roles in the same chain
- **Persistent memory** -- Shared project knowledge, per-hero notes, auto-summarization, ADRs. Heroes learn and improve over time
- **Cost tracking** -- Per-session token tracking with daily caps and auto-pause

**Tech stack:** Rust CLI (single binary), Python agents (Claude Code SDK), React dashboard with pixel art guild hall theme, SQLite for state.

**What works today:** Full CLI (`guild init`, `guild goal`, `guild recruit`, etc.), Guild Master autonomous loop, quest chain automation, git workflow (branch/PR), Telegram notifications, memory system, MCP integration, cost tracking, dashboard with real-time updates.

**What's next:** Cross-repo quest chains, webhook support, natural language Telegram interaction.

Built for macOS/Linux. Requires Claude API key.

GitHub: [link]

Would love feedback on the architecture and agent coordination approach. Happy to answer questions about multi-agent orchestration patterns.
