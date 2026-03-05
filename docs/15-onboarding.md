# 15 — Onboarding Flow

---

## `guild init` — Fresh Setup

```
[1/6] Welcome to Guild
      Checking system requirements...
      ✓ git 2.x found
      ✓ Python 3.11+ found
      ? Enter your Anthropic API key: sk-ant-...
      ✓ API key valid

[2/6] Guild workspace
      Creating ~/.guild/
      ✓ Directory structure created
      ✓ SQLite database initialized
      ✓ Default shared memory templates written

[3/6] Telegram (optional but recommended)
      ? Set up Telegram notifications? (Y/n): Y
      → Create a bot via @BotFather, then paste the token:
      ? Bot token: 123456:ABC...
      ? Chat ID (send /start to your bot first): 98765432
      ✓ Test message sent — check your Telegram

[4/6] License
      ? License key (Enter for Free tier): 
      ✓ Free tier active (2 heroes max)

[5/6] Recruit first hero
      Classes:
        1. Rust Sorcerer    rust, wasm, systems
        2. Python Sage      python, ml, data
        3. Node Assassin    node, typescript, api
        4. DevOps Paladin   devops, kubernetes, azure
        5. Frontend Archer  react, typescript, css
        6. Data Shaman      sql, etl, databricks
        7. ML Engineer      ml, pytorch, llm

      ? Class (1-7): 1
      ? Name (Enter for random): StormForge
      ✓ Hero StormForge (Rust Sorcerer) created

      To start this hero, run in a new terminal:
        guild hero StormForge --start
      (command copied to clipboard)

[6/6] Register a project
      ? Register a project now? (Y/n): Y
      ? Path: ./my-project
      ? Name: greentic
      ✓ Project registered
      ✓ Branch protection configured
      ✓ Shared memory template created

      Setup complete.
      Run `guild status` to see your guild.
      Run `guild goal "..."` to get started.
```

---

## `guild project add` — Add Project to Existing Guild

```
$ guild project add --path ./my-repo

Registering: my-repo
? Project name: map-group
? Primary language: TypeScript
? Main branch: main
? Dev branch (created if not exists): development
? Git provider: GitHub

Scanning repository...
✓ Node.js, TypeScript, Jest detected
✓ Existing conventions read into shared memory
✓ Branch 'development' created from 'main'
✓ Branch protection rules configured
✓ Shared memory template created: memory/shared/projects/map-group.md

Registered. Assign quests with:
  guild goal --project map-group "..."
```

---

## `guild hero {name} --start`

Run in a new terminal tab:

```
$ guild hero StormForge --start

Starting: StormForge (Rust Sorcerer)
Assembling CLAUDE.md...
✓ 0 active quests | 0 project memories

Launching Claude Code...
────────────────────────────────────────
Hero StormForge ready. Waiting for quest.
/guild-status → current state
/guild-help   → available commands
────────────────────────────────────────
```

---

## First Goal Experience

```bash
$ guild goal "Build a REST API endpoint for daily sales report"
```

```
Guild Master analyzing...

Project detected: map-group (TypeScript, Node.js)
Decomposing...

Quest Chain GLC-001: REST API — Daily Sales Report
├── GLD-001 [RARE]   Implement GET /reports/daily-sales
│   Branch: feature/GLD-001-daily-sales-endpoint
│   Assigned: StormForge ✓
│
├── GLD-002 [COMMON] Write integration tests
│   Assigned: pending (after GLD-001 completes)
│
└── GLD-003 [COMMON] Code review GLD-001 PR
    Assigned: pending (after GLD-002 completes)

StormForge notified. GLD-001 is active.
```

---

## Rookie Period (first 7 days)

During the rookie period, Guild Master operates more conservatively:

- Does not auto-merge to `development` without developer confirmation
- Sends more frequent status updates (lower Level 2 → 3 threshold)
- Includes "why I did this" explanation on every autonomous action
- Suggests when to recruit second and third heroes

Skip with: `guild config --skip-rookie`
