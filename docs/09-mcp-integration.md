# 09 — MCP Integration

Heroes can be equipped with MCP (Model Context Protocol) servers that give them access to external tools and services. Each hero gets a different MCP configuration depending on their class, the project they're working on, and the quest requirements.

---

## MCP Registry Schema

```sql
CREATE TABLE mcp_servers (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  display_name  TEXT NOT NULL,
  url           TEXT,                  -- URL-type MCP
  command       TEXT,                  -- process-type MCP
  args          JSON,
  env_vars      JSON,                  -- references guild secrets
  skills_served JSON,                  -- skills this MCP enables
  status        TEXT DEFAULT 'active',
  added_at      DATETIME NOT NULL
);

CREATE TABLE hero_mcps (
  hero_id      TEXT NOT NULL,
  mcp_id       TEXT NOT NULL,
  auto_attach  BOOLEAN DEFAULT false,  -- always include in sessions?
  added_at     DATETIME NOT NULL,
  PRIMARY KEY (hero_id, mcp_id)
);
```

---

## Built-in MCPs

All heroes receive these by default. Cannot be removed.

| MCP | Purpose |
|---|---|
| `filesystem` | Read/write scoped to guild workspace + assigned project |
| `git` | Branch, commit, push operations |

---

## MCP-to-Skill Mapping

Each MCP declares which skills it enables. Guild Master uses this for auto-attach decisions.

| MCP | Skills Served |
|---|---|
| `github-mcp` | github, pr-management, code-review |
| `gitlab-mcp` | gitlab, pr-management, code-review |
| `databricks-mcp` | databricks, spark, etl |
| `postgres-mcp` | sql, postgres, data |
| `kubernetes-mcp` | kubernetes, k8s, devops |
| `azure-mcp` | azure, azure-functions, devops |
| `slack-mcp` | slack, notifications |
| `telegram-mcp` | telegram, messaging |
| `notion-mcp` | notion, docs, planning |
| `clickup-mcp` | clickup, task-management |

---

## Auto-Attach Logic

Guild Master determines which MCPs to include per session:

```
1. Always:    filesystem, git (built-in)
2. Permanent: hero_mcps WHERE auto_attach = true
3. Quest:     MCPs WHERE skills_served overlaps quest.req_skills
4. Project:   project.default_mcps (configured per project)
```

Example:

```
Hero: StormForge
Quest: GLD-055 "Push test results to Databricks"
Project: map-group (default MCPs: github-mcp)

Session MCPs:
  ✓ filesystem       (built-in)
  ✓ git              (built-in)
  ✓ github-mcp       (project default)
  ✓ databricks-mcp   (quest req_skills: databricks)
```

---

## Generated MCP Config

Written to `workspace/heroes/{name}/mcp-config.json` at session start:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem",
               "/home/user/guild/workspace",
               "/home/user/projects/greentic"]
    },
    "git": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-git"]
    },
    "databricks-mcp": {
      "url": "https://adb-xxx.azuredatabricks.net/mcp",
      "env": { "DATABRICKS_TOKEN": "{secret:DATABRICKS_TOKEN}" }
    }
  }
}
```

Secrets are resolved at generation time — plain text never written to disk.

---

## Secrets Management

```bash
guild secret add GITHUB_TOKEN ghp_xxxx
guild secret add DATABRICKS_TOKEN dapi_xxxx
guild secret list                               # shows names only, never values
guild secret remove GITHUB_TOKEN
```

Encryption key derived from machine ID + user home directory. Secrets are not portable across machines by default.

---

## Custom MCP Registration

```bash
# URL-based MCP
guild mcp add \
  --name "internal-api" \
  --url "http://localhost:3001/mcp" \
  --skills "internal-api,reporting" \
  --display-name "Internal API"

# Process-based MCP
guild mcp add \
  --name "custom-db" \
  --command "python" \
  --args "-m my_mcp_server" \
  --skills "custom-db,analytics" \
  --env "DB_URL={secret:DATABASE_URL}"

# Attach to hero (permanent)
guild mcp attach StormForge github-mcp --auto

# Attach to project (all heroes working here get it)
guild mcp attach --project greentic databricks-mcp

# List and status
guild mcp list
guild mcp status
```

---

## Guild Master MCP Config

Guild Master has its own MCP set focused on orchestration, not implementation:

```
Always active:    filesystem, git, github-mcp (or gitlab-mcp), telegram-mcp
If configured:    slack-mcp, clickup-mcp, notion-mcp
```

Guild Master does not execute code. Its MCPs are for coordination and communication only.

---

## MCP Failure Handling

| Scenario | Response |
|---|---|
| Required MCP unreachable | Abort session start, mark quest blocked, notify developer |
| Optional MCP unreachable | Start session without it, log warning, include in daily report |
| MCP crashes mid-session | Hero continues without it, logs warning, reports in outbox |
