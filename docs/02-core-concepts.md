# 02 — Core Concepts

## The Guild

The Guild is the top-level entity — a folder on the developer's machine containing all agents, memory, and operational state. A single Guild serves multiple projects. Agents are not bound to one project; they can be dispatched to any project the Guild knows about.

```
~/guild/
  agents/     memory/     quests/     workspace/     guild.db
```

---

## Guild Master

The Guild Master is a permanently running autonomous agent — the orchestrator. It is not a human-facing chatbot. It is a decision-making process that:

- Receives high-level goals from the developer
- Decomposes goals into quest chains
- Assigns quests to heroes based on skills and availability
- Monitors progress and handles blockers autonomously
- Manages the full git lifecycle from branch creation to merge
- Proactively surfaces issues, runs scheduled checks, and notifies the developer

> **Key principle:** The Guild Master resolves **reversible** decisions autonomously and escalates **irreversible** decisions to the developer. Committing code is reversible. Merging to main, deleting files, and new architectural decisions require confirmation.

---

## Heroes

Heroes are specialized Claude Code agents, each representing a running or standby terminal session. Every hero has:

- **A class** — defining their skill set (e.g., Rust Sorcerer, DevOps Paladin)
- **A persistent identity** — name, level, XP, and quest history that survive session restarts
- **Private memory** — a `CLAUDE.md` auto-injected at session start
- **Shared memory access** — read access to guild-wide project knowledge

Recruiting a hero means generating a Claude Code session command with a pre-configured system prompt. Starting a new hero equals opening a new Claude Code terminal session with that command.

> **Minimum viable guild:** A functioning quest chain requires at least 3 heroes — implementor, tester, and reviewer. Free tier supports 2 heroes (limited workflow). Pro tier supports up to 8.

---

## Quests

A quest is a single, bounded unit of work assigned to one hero. Quests follow a strict lifecycle and belong to a quest chain.

### Quest Tiers

| Tier | Complexity | Party Size | Description |
|---|---|---|---|
| Common | Simple | 1 hero | Single file change, small fix, docs update |
| Rare | Medium | 2 heroes | Multi-file feature |
| Epic | Complex | 2 heroes | Significant feature, full chain |
| Legendary | Major | 3 heroes | Large system change, extra review |
| Boss | Critical | 4 heroes | Architectural change — must be decomposed first |

---

## Quest Chains

A quest chain is the full lifecycle of a piece of work — from implementation to merge. Every non-trivial quest must complete the full chain.

### Standard Chain

1. **Implementation** — specialist hero, creates feature branch
2. **Test** — different hero, tests on same branch
3. **Review** — third hero, reviews PR
4. **Merge** — executed by Guild Master after approval

> **Chain rule:** No hero may hold more than one role in the same quest chain. The implementor cannot be the tester. The tester cannot be the reviewer. This is enforced by the Guild Master at assignment time.
