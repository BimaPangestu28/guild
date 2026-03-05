# 14 — Feature Scope

---

## v1.0 — Must Have (P0/P1)

| Feature | Priority | Notes |
|---|---|---|
| Guild Master agent loop | P0 | Core orchestration, quest decomposition, assignment |
| Hero management | P0 | Recruit, retire, session command generation |
| Persistent memory system | P0 | Shared + private, CLAUDE.md injection |
| Quest chain system | P0 | impl → test → review → merge lifecycle |
| Git workflow enforcement | P0 | Branch creation, PR management, merge control |
| Project management | P0 | Register, configure, pause, archive, remove |
| Multi-repo project groups | P1 | Group repos under one logical project |
| Self-hosted installer | P0 | Single binary, `guild init`, zero external deps |
| Skill system | P1 | Base + learned skills, proficiency, auto-learn |
| MCP integration | P1 | Registry, auto-attach, custom MCPs, secrets |
| Local dashboard | P1 | Hero status, quest board, activity log |
| Telegram notifications | P1 | Two-way — briefings, commands, approvals |
| Proactive behaviors | P1 | Idle assignment, health scan, TODO detection |
| Cost tracking | P1 | Token usage per hero, quest, project |
| CLI interface | P0 | Full command set — see Section 12 |
| Conflict resolution | P0 | File locking, merge conflict handling |
| Error handling & recovery | P0 | Crash recovery, rate limits, git failures |

---

## v1.x — Nice to Have

| Feature | Priority | Target |
|---|---|---|
| Multiple Guild Master personalities | P2 | v1.1 |
| Quest templates per project type | P2 | v1.1 |
| Memory export and import | P2 | v1.1 |
| GitHub Actions integration | P2 | v1.1 |
| Slack notifications (alternative to Telegram) | P3 | v1.2 |
| Hero performance analytics | P3 | v1.2 |
| Sprint planning mode | P2 | v1.2 |
| Quest dependency visualization | P3 | v1.2 |

---

## Explicitly Out of Scope (v1)

- Cloud sync or remote state
- Multi-user or team collaboration
- Mobile application
- Support for non-Claude AI models
- Integration with project management tools (Jira, Linear, ClickUp)
- IDE plugins or editor extensions
- Windows support (v1 targets macOS and Linux only)
