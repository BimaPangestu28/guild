# 16 — Error Handling

---

## Error Classification

| Class | Behavior |
|---|---|
| `FATAL` | Guild stops entirely. Developer must intervene manually. |
| `CRITICAL` | Affected component pauses. Developer notified immediately via Telegram Level 4. |
| `WARNING` | Guild continues. Logged. Included in next daily report. |
| `INFO` | Guild continues. Logged only. |

---

## Guild Master Errors

| Error | Class | Recovery |
|---|---|---|
| Process crash | CRITICAL | Auto-restart after 30s. Re-read last state from guild.db. |
| Stuck (no output > 10 min) | CRITICAL | Kill and restart. Log last known action. |
| Daily cost cap exceeded | CRITICAL | Pause all hero sessions. Notify developer with usage summary. |
| guild.db corruption | FATAL | Stop. Notify developer. Restore from hourly auto-backup. |
| Cannot parse developer goal | WARNING | Request clarification via Telegram. Do not guess. |

---

## Hero Session Errors

| Error | Class | Recovery |
|---|---|---|
| Process crash | WARNING | Auto-restart (max 3 retries). See Section 07 crash recovery. |
| Crash 3x on same quest | CRITICAL | Mark quest blocked. Notify developer. No further retry. |
| Invalid outbox format | WARNING | Parse best-effort. If unrecoverable, treat as blocked. |
| Modifies file outside assigned project | CRITICAL | Revert via git. Suspend hero. Notify developer. |
| Attempts to push to main | FATAL | Block push (branch protection). Suspend hero. Notify immediately. |
| API auth error | CRITICAL | Pause hero. Notify developer to check API key. |

---

## Git Operation Errors

| Error | Class | Recovery |
|---|---|---|
| Branch creation fails (already exists) | WARNING | If same quest: reuse. If different: append `-v2` suffix. |
| PR creation fails (API error) | WARNING | Retry 3x with exponential backoff. If all fail, log and report. |
| Merge conflict on PR | INFO | Auto-create conflict resolution quest (Section 10, Scenario B). |
| Merge to development fails | WARNING | Retry once. If fail, notify developer via Telegram Level 3. |
| Branch protection setup fails on init | WARNING | Log warning. Remind developer to set manually. Continue init. |

---

## Memory Errors

| Error | Class | Recovery |
|---|---|---|
| CLAUDE.md assembly fails | WARNING | Use last known good CLAUDE.md. Log which sections failed. |
| Shared memory write conflict | INFO | Section 10 Scenario C — Guild Master resolves. |
| Memory file exceeds 50KB | WARNING | Auto-summarize. Archive old content to history subfolder. |
| guild.db write fails | CRITICAL | Stop current operation. Attempt write to backup location. Notify developer. |

---

## Notification Errors

| Error | Class | Recovery |
|---|---|---|
| Telegram API unreachable | INFO | Queue notifications. Retry every 5 min. Show queued in dashboard. |
| Telegram bot token invalid | WARNING | Disable Telegram. Fall back to dashboard-only. Remind on next `guild status`. |

---

## MCP Errors

| Error | Class | Recovery |
|---|---|---|
| Required MCP unreachable on session start | CRITICAL | Abort session start. Mark quest blocked. Notify developer. |
| Optional MCP unreachable | WARNING | Start session without it. Log warning. Include in daily report. |
| MCP crashes mid-session | WARNING | Hero continues without it. Logs warning. Reports in outbox. |

---

## Auto-Backup

`guild.db` is backed up automatically every hour to `~/.guild/backups/guild-{timestamp}.db`. Last 24 backups are retained.

```bash
# List backups
guild backup list

# Restore from backup
guild backup restore guild-2026-03-06-08-00.db
```
