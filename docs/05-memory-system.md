# 05 — Memory System

Memory is what separates Guild from "just running multiple Claude Code sessions." Heroes accumulate knowledge about your codebase over time. The longer Guild runs, the smarter every session starts.

---

## Memory Architecture

```
memory/
  shared/                           ← readable by all heroes and Guild Master
    projects/
      {name}.md                     ← architecture, patterns, project context
      {name}-adr/                   ← architectural decision records per project
        adr-001-use-tokio.md
        adr-002-wasm-interface.md
    conventions/                    ← global coding standards, git conventions
  heroes/
    {name}/                         ← private per hero
      CLAUDE.md                     ← hot context, injected at session start
      history.md                    ← quest log
      notes.md                      ← personal working memory
      skills/                       ← skill backing files (see Section 08)
        {skill-name}.md
```

---

## Memory Layers

### Shared Memory — Guild-wide

Readable by all heroes and Guild Master. Written by any hero when a learning is project-relevant.

**`shared/projects/{name}.md`** — the most important file. Contains:
- Project architecture overview
- Known patterns and anti-patterns
- Key files and what they do
- Dependencies and why they were chosen
- Deployment and build notes

**`shared/projects/{name}-adr/`** — Architecture Decision Records. Every significant technical decision gets an ADR:

```markdown
# ADR-001: Use Tokio for Async Runtime

Date: 2026-03-01
Status: ACCEPTED
Decided by: StormForge (from quest GLD-023)

## Context
Needed async runtime for WASM adapter host.
Evaluated: tokio, async-std, smol

## Decision
Use tokio. Most mature ecosystem, best compatibility with existing dependencies.

## Consequences
- wasm-bindgen-futures works well with tokio
- Cannot easily switch later — all async code assumes tokio
- Performance meets requirements (benchmarked in GLD-023)
```

**`shared/conventions/`** — Global standards:
- `git.md` — branch naming, commit format, PR etiquette
- `code-style.md` — language-specific style rules
- `testing.md` — testing standards, coverage thresholds

### Private Memory — Per Hero

Each hero has a directory that only they read and write. Injected at session start.

**`CLAUDE.md`** — hot context. Assembled dynamically before each session (see below).

**`history.md`** — running log of all completed quests:

```markdown
## 2026-03-06
- GLD-042 Implement Telegram Adapter [DONE] 2h14m
- GLD-044 Review Slack PR [DONE] 45m

## 2026-03-05
- GLD-038 Fix WASM memory leak [DONE] 1h02m
```

**`notes.md`** — personal working memory. Things the hero has noticed but haven't become shared knowledge yet:

```markdown
## Observations
- src/runtime/host.rs gets touched almost every quest — worth knowing well
- Integration tests are slow (45s+) — run unit tests first to fail fast
- Maarten prefers small focused commits over large ones (from code review feedback)
```

---

## CLAUDE.md Injection

Every hero session is started with a dynamically generated `CLAUDE.md` assembled from three sources:

1. **Hero identity** — class, skills, focus area, guild rules (static template)
2. **Current quest context** — objective, branch, project pointer, chain status
3. **Personal context** — contents of `notes.md` and last 5 entries from `history.md`
4. **Project context** — contents of `shared/projects/{project}.md` (relevant section)

The full CLAUDE.md template:

```markdown
# {HERO_NAME} — {HERO_CLASS}

## Identity
You are {HERO_NAME}, a {HERO_CLASS} in the Code Guild.
Specialty: {FOCUS}
Skills: {BASE_SKILLS} + {LEARNED_SKILLS}

## Current Quest
ID: {QUEST_ID}
Objective: {QUEST_TITLE}
Description: {QUEST_DESCRIPTION}
Branch: {BRANCH_NAME}
Project: {PROJECT_NAME} at {PROJECT_PATH}
Chain: {CHAIN_ID} — your role: {ROLE} (impl|test|review)

## Project Context
{contents of shared/projects/{project}.md}

## Your Personal Context
{contents of heroes/{name}/notes.md}
{last 5 entries from heroes/{name}/history.md}

## Skill Context
{contents of heroes/{name}/skills/{relevant_skill}.md — for skills matching project}

## Memory Update Protocol
At the end of this session, you MUST:
1. Write to workspace/outbox/{name}.md:
   - status: done | blocked
   - summary: what was accomplished
   - files_changed: list
   - learnings: new codebase knowledge discovered
   - blockers: if status is blocked, describe precisely

2. Update memory/heroes/{name}/CLAUDE.md:
   - Remove current quest section
   - Append to history

3. Update memory/heroes/{name}/notes.md:
   - Add any new personal observations

4. If architectural decision was made:
   - Write ADR to memory/shared/projects/{project}-adr/

5. If significant codebase knowledge was gained:
   - Append to memory/shared/projects/{project}.md

## Guild Rules
- Work only in {PROJECT_PATH} and guild workspace directories
- Commit incrementally — do not wait until the end
- Commit format: [GLD-{id}] {description} — {your_name}
- If blocked, report immediately — do not guess or work around
- Never push to main directly
- Never merge your own PR
```

---

## Memory Update Protocol

Heroes follow this protocol at the end of every session — enforced via CLAUDE.md instruction.

### Outbox Format

```markdown
# Quest GLD-042 — StormForge
Status: done
Time: 2h 14m
Branch: feature/GLD-042-telegram-adapter

## Summary
Implemented TelegramAdapter struct implementing MessageAdapter trait.
Covers send_message, receive_message, and webhook handling.

## Files Changed
- src/adapters/telegram.rs (new, 280 lines)
- src/adapters/mod.rs (modified — added telegram module export)
- Cargo.toml (modified — added teloxide dependency)

## Learnings
- teloxide crate handles bot lifecycle well, worth using for other Telegram work
- Bot API rate limit is 30 msg/sec per chat — documented this in shared memory
- MessageAdapter trait needed one new method: supports_webhook() — added to trait

## Blockers
none
```

### What Goes Where

| Learning type | Destination |
|---|---|
| Architectural decision | `shared/projects/{name}-adr/adr-NNN.md` |
| Project-wide pattern | `shared/projects/{name}.md` |
| Personal observation | `heroes/{name}/notes.md` |
| Skill knowledge | `heroes/{name}/skills/{skill}.md` |

> **Memory grows over time.** A hero recruited today will, after 10 quests, have deep context about your architecture, patterns, and decisions. A newly recruited hero on a known project immediately gets shared memory context — cold start is almost eliminated.

---

## Memory Maintenance

### Auto-summarization

When a memory file exceeds 50KB, Guild Master auto-summarizes:

1. Archive current content to `memory/heroes/{name}/archive/{date}-notes.md`
2. Ask Guild Master to summarize the most important points
3. Write condensed version back to the original file
4. Log summarization event

### Manual Memory Commands

```bash
# View shared memory for a project
guild memory --project greentic

# View hero private memory
guild memory --hero StormForge

# View specific ADR
guild memory --project greentic --adr 001

# Edit memory directly (opens in $EDITOR)
guild memory edit --project greentic
guild memory edit --hero StormForge --file notes

# Clear hero private memory (e.g., before reassigning to new domain)
guild memory clear --hero StormForge --private

# Export all memory (for backup or migration)
guild memory export --output ./guild-memory-backup.tar.gz
```
