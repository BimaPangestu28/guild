# 07 — Hero Lifecycle

## State Machine

```
OFFLINE ──recruit──► IDLE ──assign──► ON_QUEST ──complete──► RESTING
                      ▲                    │                      │
                      │                    ▼                      │
                      │               BLOCKED                     │
                      │                    │                      │
                      └────────────────────┴──────(30 min)────────┘
```

| State | Process Running | Assignable | Description |
|---|---|---|---|
| `offline` | No | No | Never recruited or manually stopped |
| `idle` | Yes | Yes | Session running, waiting for quest |
| `on_quest` | Yes | No | Actively executing a quest |
| `resting` | Yes | No | Quest done, cooling down 30 min |
| `blocked` | Yes | No | Cannot proceed, waiting for resolution |

---

## Session Start Sequence

```
1. guild.db: set hero.status = 'idle', hero.session_pid = null
2. memory_manager: assemble CLAUDE.md from:
   - hero class template (static)
   - hero private notes (heroes/{name}/notes.md)
   - current quest context if exists
   - project shared memory (shared/projects/{project}.md)
3. Write assembled CLAUDE.md to memory/heroes/{name}/CLAUDE.md
4. process_manager: spawn Claude Code session with CLAUDE.md path
5. guild.db: set hero.session_pid = {pid}, hero.last_active = now()
6. watcher: register outbox/{name}.md for file change events
```

---

## Quest Assignment Sequence

```
1. guild.db: set quest.status = 'active', quest.assigned_to = hero.id
2. guild.db: set hero.status = 'on_quest', hero.current_quest_id = quest.id
3. git: create branch {type}/GLD-{id}-{slug} from development
4. memory_manager: update hero CLAUDE.md with quest context
5. Write quest brief to workspace/inbox/{hero_name}.md
6. Hero session detects inbox file change (via watcher)
7. Hero reads inbox, begins execution
```

---

## Quest Completion Sequence

```
1. Hero writes to workspace/outbox/{name}.md
2. Hero updates memory/heroes/{name}/CLAUDE.md
3. Hero updates memory/heroes/{name}/history.md
4. Hero writes to shared memory if applicable
5. Hero git commits: "[GLD-{id}] {quest_title} — {hero_name}"
6. watcher detects outbox change → triggers Guild Master cycle
7. Guild Master reads outbox, validates completion
8. Guild Master: quest.status = 'done', hero.status = 'resting'
9. Guild Master: auto-spawn next chain quest
10. After 30 min: hero.status = 'idle', check backlog
```

---

## Session Crash Recovery

```
1. process_manager detects dead PID (heartbeat every 60s)
2. guild.db: hero.status = 'offline', hero.session_pid = null
3. Check current quest state:
   a. Recent commits exist → re-spawn hero, re-inject context with recovery block
   b. No commits → reset quest to backlog, re-spawn hero
4. Notify developer via Telegram Level 3 if quest was active
```

Recovery block injected into CLAUDE.md:

```markdown
## ⚠ RECOVERY CONTEXT
Previous session ended unexpectedly.
Last known action: {last_log_entry}
Last commit: {hash} — "{message}"
Quest status at crash: {status}

Resume from last commit. Do not redo completed work.
Run tests before continuing if unsure about state.
```

---

## Rate Limit Handling

```
1. Hero session pauses (SDK behavior)
2. process_manager detects no output > 5 minutes
3. If rate limit confirmed:
   a. hero.status = 'resting' (temporary)
   b. Calculate retry time from rate limit headers
   c. Schedule re-activation after cooldown
   d. Log to activity — no Telegram (routine)
4. If other cause → treat as crash (above)
```

---

## Manual Session Control

```bash
guild pause StormForge        # SIGTERM session, status → offline
guild resume StormForge       # re-spawn, inject last known context
guild pause --all
guild resume --all
```

On `pause`, Guild Master commits any uncommitted changes:
```
[GLD-{id}] WIP — paused by developer — {hero_name}
```
