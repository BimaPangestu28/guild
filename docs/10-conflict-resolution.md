# 10 — Conflict Resolution

Guild Master is the single source of truth for state. Heroes can only write to their own memory and their assigned project scope. All conflicts are resolved by Guild Master — escalated to developer only when necessary.

---

## File-Level Locking

Guild Master tracks all files being edited by active quests:

```sql
CREATE TABLE file_locks (
  file_path  TEXT NOT NULL,
  quest_id   TEXT NOT NULL,
  hero_id    TEXT NOT NULL,
  locked_at  DATETIME NOT NULL,
  PRIMARY KEY (file_path)
);
```

Before assigning a quest, Guild Master parses the quest description to identify likely files and checks for existing locks. Overlapping quests are queued until the lock is released.

---

## Conflict Scenarios

### Scenario A — Two heroes need the same file

```
Hero A: on GLD-042, editing src/adapters/telegram.rs
Hero B: assigned GLD-045, also needs src/adapters/telegram.rs

Resolution:
→ GLD-045 queued with note: "waiting for GLD-042 lock release"
→ GLD-042 merges → lock released → GLD-045 auto-activates
→ Developer not notified (routine, handled autonomously)
```

### Scenario B — Merge conflict on PR

```
Hero A PR merged to development
Hero B PR now conflicts with development

Resolution:
→ Guild Master detects conflict via provider API
→ Auto-create chore quest: "Resolve merge conflicts GLD-{id}"
→ Assign to original implementor, same branch
→ Re-run test and review chain after resolution
```

### Scenario C — Shared memory conflict

```
Hero A writes: "Use tokio for async"
Hero B writes: "Use async-std for async"
(to the same shared memory file, within 30s)

Resolution:
→ If existing ADR covers it → follow ADR, discard conflicting entry
→ If no ADR → write both options to new ADR marked "PENDING DECISION"
→ Notify developer via Telegram Level 3 with A/B choice
→ Developer replies → Guild Master resolves and updates ADR
```

### Scenario D — Dependency detected late

```
GLD-042: "Refactor MessageAdapter trait"
GLD-043: "Implement SlackAdapter using MessageAdapter"
→ Hero B reports blocked: "MessageAdapter interface not stable yet"

Resolution:
→ Guild Master identifies GLD-043 depends on GLD-042
→ GLD-043.status = 'backlog', dependency recorded in guild.db
→ GLD-043 auto-activates when GLD-042 chain completes
→ Guild Master logs: "Late dependency detected — improving heuristic"
```

---

## Developer Override Rule

If developer instruction conflicts with a Guild Master decision:

```
1. Guild Master stops conflicting action immediately
2. Logs the conflict and override in activity log
3. Updates shared memory / ADR to reflect developer decision
4. Resumes with developer instruction
5. Does NOT ask for justification
```

Developer always wins. No exceptions.
