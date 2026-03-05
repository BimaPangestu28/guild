# 19 — Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Claude Code SDK breaking changes | High | Isolate SDK behind adapter layer. One interface, swappable implementation. |
| User cost shock from parallel agents | High | Cost tracking is P1. Daily cap configurable. Warning at 80% of cap. Auto-pause at 100%. |
| Agent infinite loop or runaway session | High | Circuit breaker in process manager. Max tokens per quest. Dead-man timer. |
| guild.db corruption or data loss | Medium | Hourly auto-backup. Markdown memory files are human-readable fallback. Git history as audit trail. |
| User expectation mismatch on autonomy | Medium | Onboarding rookie period frames Guild as junior team, not oracle. Review everything. |
| Two heroes editing same file | Low | File-level locking in guild.db. Guild Master enforces at assignment time. |
| Git provider API downtime | Low | Local git operations continue. PR creation queued and retried. Developer notified. |
| MCP server unavailability | Low | Required MCP: block quest, notify. Optional MCP: continue without it. |
| Memory file grows unbounded | Low | Auto-summarize at 50KB. Archive history. Guild Master monitors memory sizes. |
| macOS / Linux compatibility gaps | Medium | Test on both platforms from Phase 1. Rust binary targets both. No Windows in v1. |
