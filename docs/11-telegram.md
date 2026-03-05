# 11 — Telegram Interface

Guild Master communicates with the developer via Telegram — both outbound notifications and inbound commands. This means you can manage your guild from your phone without opening a terminal.

---

## Architecture

Guild uses **polling mode** by default (long polling Telegram API every 10s). No public endpoint required. Webhook mode available for lower latency.

```
Developer ──message──► Telegram Bot ──polling──► Guild HTTP listener (localhost:7432)
                                                         │
                                              Guild Master processes
                                                         │
Developer ◄──message── Telegram Bot ◄──API── Guild Master response
```

---

## Inbound Commands

### Structured (prefixed with `/`)

```
/status                     Hero roster and active quests overview
/report                     Latest Guild Master analysis
/heroes                     Hero roster with status and level
/quests                     Quest board — active, backlog, blocked
/pause                      Pause all hero sessions
/resume                     Resume all hero sessions
/approve {chain_id}         Approve development → main merge
/reject {chain_id}          Reject merge, keep on development
/goal {text}                Post new goal
/cost                       Today's token usage and cost breakdown
/help                       List all commands
```

### Natural Language (no prefix)

Sent to Guild Master as free-text inbox. Guild Master parses intent and acts:

```
"Focus on greentic today, pause MAP Group quests"
"StormForge seems stuck, check on it"
"Skip the test for GLD-042, it's a hotfix"
"Add a frontend hero"
```

### Parse Rules

```
Contains approval keywords + recent merge request → treat as /approve
Contains pause/stop/hold keywords → treat as /pause
Contains hero name + action → apply to that hero
Contains technical task description → treat as /goal
Ambiguous (confidence < 60%) → ask for clarification, do not execute
```

---

## Outbound Notification Formats

### Quest completion

```
✅ Quest GLD-042 merged to development
Chain: Implement Telegram Adapter
Hero: StormForge | Time: 2h 14m | +150 XP

development is 3 commits ahead of main.
```

### Daily briefing

```
☀️ Guild Briefing — Friday, 7 March

ACTIVE (2)
• GLD-043 Slack adapter — StormForge, ~3h remaining
• GLD-044 Test Slack adapter — awaiting GLD-043

BACKLOG (4)
• GLD-045 Fix rate limiter [HIGH]
• GLD-046 Update README
• ... +2 more

HEROES
• StormForge → on quest
• IronWeave  → idle ✓

TODAY'S COST: $0.84 / $5.00 cap

No blockers. No action needed.
```

### Escalation — requires decision

```
⚠️ ESCALATION — Decision Required

GLD-045: Fix WebSocket reconnect logic
Hero blocked (2nd time).

PROBLEM
Unclear: exponential backoff or fixed retry interval.
No ADR covers this.

OPTIONS
A) Exponential backoff (standard practice)
B) Fixed 5s interval (matches existing pattern)

Reply A or B.
Reply /skip to defer.
```

### Merge approval request

```
🔀 Ready to merge → main

development → main
Commits: 8 | Tested: 14 min ago ✓ | Coverage: 84% (+2%)

Changes:
• Telegram adapter (GLD-042)
• Slack adapter (GLD-043)
• Rate limiter fix (GLD-045)

Reply /approve GLC-001 to merge.
Reply /reject GLC-001 to keep on development.
```

### Cost warning

```
⚠️ COST WARNING

Daily usage: $4.32 / $5.00 cap (86%)

Top consumers:
• StormForge  $2.10  (complex quest)
• IronWeave   $1.80  (large test suite)

Auto-pause at $5.00.
Reply /cost-extend {amount} to raise today's cap.
```

---

## Conversation Context

Guild Master stores the last 10 messages per Telegram chat in `guild.db` as context. This enables natural follow-up:

```
Developer: "What's StormForge working on?"
Guild:     "GLD-043 — Slack adapter. ~3h remaining. Last commit: 22 min ago."
Developer: "How long has that been going?"
Guild:     "GLD-043 started 4h 38min ago."
```

Context clears daily at morning briefing time.

---

## Setup

```bash
guild setup telegram
```

Walks through:
1. Create bot via @BotFather
2. Enter bot token
3. Auto-detect chat ID (send any message to bot first)
4. Send test message
5. Configure notification levels
