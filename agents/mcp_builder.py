#!/usr/bin/env python3
"""
MCP Builder — assembles MCP server configurations for hero sessions.

Reads from the guild database and produces Claude Code-compatible
MCP config JSON for each hero, resolving secrets and checking health.
"""

import json
import os
import re
import shutil
import sqlite3
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

GUILD_DIR = Path.home() / ".guild"
DB_PATH = GUILD_DIR / "guild.db"
SECRETS_PATH = GUILD_DIR / "secrets.json"
WORKSPACE_DIR = GUILD_DIR / "workspace"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# 1. build_mcp_config
# ---------------------------------------------------------------------------

def build_mcp_config(hero_id, quest_id=None):
    """Assemble MCP config JSON for a hero session.

    Merges:
      - Permanent MCPs: hero_mcps WHERE auto_attach=1
      - Quest-based MCPs: mcp_servers WHERE skills_served overlaps quest.req_skills
      - Project default MCPs: from projects.default_mcps JSON

    Returns dict in Claude Code MCP config format:
        {
            "mcpServers": {
                "server-name": {
                    "command": "...",
                    "args": ["..."],
                    "env": {}
                }
            }
        }
    """
    conn = get_db()
    config = {"mcpServers": {}}

    # --- Permanent MCPs (auto_attach=1 for this hero) ---
    auto_mcps = conn.execute(
        "SELECT m.* FROM mcp_servers m "
        "JOIN hero_mcps hm ON m.id = hm.mcp_id "
        "WHERE hm.hero_id = ? AND hm.auto_attach = 1 AND m.status = 'active'",
        (hero_id,),
    ).fetchall()

    for mcp in auto_mcps:
        _add_mcp_to_config(config, mcp)

    # --- Quest-based MCPs (skill overlap) ---
    if quest_id:
        quest = conn.execute(
            "SELECT req_skills, project_id FROM quests WHERE id = ?",
            (quest_id,),
        ).fetchone()

        if quest:
            req_skills = _parse_json_list(quest["req_skills"])

            if req_skills:
                # Find MCP servers whose skills_served overlaps with quest req_skills
                all_mcps = conn.execute(
                    "SELECT * FROM mcp_servers WHERE status = 'active'"
                ).fetchall()

                for mcp in all_mcps:
                    mcp_skills = _parse_json_list(mcp["skills_served"])
                    if mcp_skills and set(s.lower() for s in mcp_skills) & set(s.lower() for s in req_skills):
                        _add_mcp_to_config(config, mcp)

            # --- Project default MCPs ---
            if quest["project_id"]:
                project = conn.execute(
                    "SELECT default_mcps FROM projects WHERE id = ?",
                    (quest["project_id"],),
                ).fetchone()

                if project:
                    default_mcp_names = _parse_json_list(project["default_mcps"])
                    for mcp_name in default_mcp_names:
                        mcp = conn.execute(
                            "SELECT * FROM mcp_servers WHERE name = ? AND status = 'active'",
                            (mcp_name,),
                        ).fetchone()
                        if mcp:
                            _add_mcp_to_config(config, mcp)

    conn.close()

    # Resolve secrets in env vars
    config = resolve_secrets(config)

    return config


def _add_mcp_to_config(config, mcp_row):
    """Add an MCP server row to the config dict (deduplicates by name)."""
    name = mcp_row["name"]
    if name in config["mcpServers"]:
        return  # Already present

    entry = {}

    if mcp_row["url"]:
        # Remote MCP — use URL-based config
        entry["url"] = mcp_row["url"]
    elif mcp_row["command"]:
        entry["command"] = mcp_row["command"]
        if mcp_row["args"]:
            # Args stored as space-separated string or JSON array
            args_raw = mcp_row["args"]
            try:
                entry["args"] = json.loads(args_raw)
            except (json.JSONDecodeError, TypeError):
                entry["args"] = args_raw.split()
        else:
            entry["args"] = []

    # Parse env_vars if present
    if mcp_row["env_vars"]:
        try:
            entry["env"] = json.loads(mcp_row["env_vars"])
        except (json.JSONDecodeError, TypeError):
            entry["env"] = {}
    else:
        entry["env"] = {}

    config["mcpServers"][name] = entry


def _parse_json_list(raw):
    """Safely parse a JSON array string, returning [] on failure."""
    if not raw:
        return []
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# ---------------------------------------------------------------------------
# 2. write_mcp_config
# ---------------------------------------------------------------------------

def write_mcp_config(hero_name, config):
    """Write MCP config to ~/.guild/workspace/heroes/{hero_name}/mcp-config.json."""
    hero_dir = WORKSPACE_DIR / "heroes" / hero_name
    hero_dir.mkdir(parents=True, exist_ok=True)

    config_path = hero_dir / "mcp-config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    return str(config_path)


# ---------------------------------------------------------------------------
# 3. resolve_secrets
# ---------------------------------------------------------------------------

def resolve_secrets(config):
    """Replace ${SECRET_NAME} placeholders in env vars with values from secrets.json.

    Only resolves at generation time — never writes plaintext secrets to config files
    unless this function is called right before passing config to the session runner.
    """
    if not SECRETS_PATH.exists():
        return config

    try:
        secrets = json.loads(SECRETS_PATH.read_text())
    except (json.JSONDecodeError, IOError):
        return config

    if not isinstance(secrets, dict):
        return config

    placeholder_re = re.compile(r"\$\{([^}]+)\}")

    for server_name, server_config in config.get("mcpServers", {}).items():
        env = server_config.get("env", {})
        if not isinstance(env, dict):
            continue

        resolved_env = {}
        for key, value in env.items():
            if isinstance(value, str):
                def _replace(match):
                    secret_key = match.group(1)
                    return secrets.get(secret_key, match.group(0))

                resolved_env[key] = placeholder_re.sub(_replace, value)
            else:
                resolved_env[key] = value

        server_config["env"] = resolved_env

    return config


# ---------------------------------------------------------------------------
# 4. check_mcp_health
# ---------------------------------------------------------------------------

def check_mcp_health(config):
    """Verify reachability of each MCP server in the config.

    - URL type: quick HTTP HEAD request
    - Command type: check command exists in PATH

    Returns dict of {name: "ok" | "unreachable"}.
    """
    results = {}

    for name, server_config in config.get("mcpServers", {}).items():
        if "url" in server_config:
            results[name] = _check_url(server_config["url"])
        elif "command" in server_config:
            results[name] = _check_command(server_config["command"])
        else:
            results[name] = "unreachable"

    return results


def _check_url(url):
    """Attempt a HEAD request to the URL."""
    try:
        req = Request(url, method="HEAD")
        with urlopen(req, timeout=5):
            pass
        return "ok"
    except (URLError, OSError, ValueError):
        return "unreachable"


def _check_command(command):
    """Check if the command exists in PATH."""
    if shutil.which(command):
        return "ok"
    return "unreachable"


# ---------------------------------------------------------------------------
# CLI entrypoint for standalone usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: mcp_builder.py <hero_name> [quest_id]")
        print("       mcp_builder.py --check <hero_name> [quest_id]")
        sys.exit(1)

    check_mode = False
    args = sys.argv[1:]
    if args[0] == "--check":
        check_mode = True
        args = args[1:]

    if not args:
        print("Error: hero_name required")
        sys.exit(1)

    hero_name = args[0]
    quest_id = args[1] if len(args) > 1 else None

    if not DB_PATH.exists():
        print("Error: Guild not initialized. Run 'guild init' first.")
        sys.exit(1)

    conn = get_db()
    hero = conn.execute("SELECT id FROM heroes WHERE name = ?", (hero_name,)).fetchone()
    if not hero:
        print(f"Error: Hero '{hero_name}' not found")
        conn.close()
        sys.exit(1)

    hero_id = hero["id"]
    conn.close()

    config = build_mcp_config(hero_id, quest_id)
    config_path = write_mcp_config(hero_name, config)

    print(f"MCP config written to: {config_path}")
    print(json.dumps(config, indent=2))

    if check_mode:
        print("\nHealth check:")
        health = check_mcp_health(config)
        for name, status in health.items():
            indicator = "OK" if status == "ok" else "UNREACHABLE"
            print(f"  {name}: {indicator}")
