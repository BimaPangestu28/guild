# 08 — Skill System

Skills determine which quests a hero gets assigned. They grow over time as heroes complete quests, making them increasingly valuable for specific projects and domains.

---

## Skill Types

**Base skills** — defined by hero class, static, cannot be removed.
```
Rust Sorcerer: rust, wasm, systems, performance
Python Sage:   python, ml, data, scripting, ai
```

**Learned skills** — gained through quest experience or added manually.
```
StormForge learned skills:
  greentic-codebase         ← from 8 quests on project greentic
  telegram-bot-patterns     ← learned after quest GLD-042
  map-group-conventions     ← added manually by developer
```

---

## Schema

```sql
CREATE TABLE hero_skills (
  id           TEXT PRIMARY KEY,
  hero_id      TEXT NOT NULL,
  name         TEXT NOT NULL,
  type         TEXT NOT NULL,         -- "base" | "learned" | "manual"
  proficiency  INT DEFAULT 1,         -- 1 (novice) → 5 (master)
  source       TEXT,                  -- quest_id or "manual"
  created_at   DATETIME NOT NULL,
  updated_at   DATETIME NOT NULL
);
```

---

## Proficiency Levels

| Quests in Domain | Level | Label |
|---|---|---|
| 1–2 | 1 | Novice |
| 3–5 | 2 | Apprentice |
| 6–10 | 3 | Journeyman |
| 11–20 | 4 | Expert |
| 21+ | 5 | Master |

---

## Skill Backing Files

Each learned skill has a knowledge file at `memory/heroes/{name}/skills/{skill}.md`:

```markdown
# greentic-codebase
Proficiency: ★★★☆☆ (3/5)
Learned from: GLD-023, GLD-031, GLD-042
Last updated: 2026-03-05

## What I know
- Workspace structure: src/adapters/, src/runtime/, src/proto/
- All adapters implement MessageAdapter trait (src/traits/mod.rs)
- WASM components compiled via wasm-pack, output to pkg/
- Tokio used for async runtime (ADR-001)

## Patterns I've used
- New adapter: copy from src/adapters/template.rs
- Proto changes: run `make proto` to regenerate bindings

## Known gotchas
- wasm-bindgen must stay pinned at 0.2.92
- src/runtime/host.rs is fragile — always test after changes
```

---

## Auto-Learn on Quest Complete

```
Quest GLD-042 completed by StormForge
Project: greentic | Files: src/adapters/telegram.rs

Guild Master:
  - "greentic-codebase" exists? YES → proficiency 2 → 3
  - New patterns in outbox? YES → append to skill file
  - New gotchas? YES → append to skill file
  - Proficiency reached 4 (Expert)? → extract to shared memory
```

---

## Assignment Scoring

Guild Master scores each available hero per quest:

```
score = (base_skill_match × 10)
      + (learned_skill_match × 15)
      + (proficiency_level × 5)
      + (prior_quests_on_project × 2)
      - (hours_since_last_rest × 1)

Assign to highest score ≥ 10.
If no hero meets threshold → queue quest, notify developer.
```

---

## Skill Sharing via Shared Memory

When a hero reaches proficiency ≥ 4 on a skill, Guild Master extracts key learnings to shared memory. Other heroes working on the same project receive this knowledge via CLAUDE.md injection — even if they don't have the explicit skill tag.

---

## Manual Skill Management

```bash
guild skill add StormForge "map-group-conventions"
guild skill remove StormForge "outdated-skill"
guild skill list StormForge
guild skill show StormForge greentic-codebase
guild skill edit StormForge greentic-codebase      # opens in $EDITOR
guild skill transfer StormForge IronWeave greentic-codebase
```
