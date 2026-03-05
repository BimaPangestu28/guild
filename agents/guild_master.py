#!/usr/bin/env python3
"""
Guild Master — orchestrator agent for the Guild system.

Watches inbox for new goals, decomposes them into quest chains,
assigns quests to heroes, and processes hero completion reports.
"""

import json
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic


GUILD_DIR = Path.home() / ".guild"
DB_PATH = GUILD_DIR / "guild.db"
INBOX = GUILD_DIR / "workspace" / "inbox"
OUTBOX = GUILD_DIR / "workspace" / "outbox"
POLL_INTERVAL = 10  # seconds

SYSTEM_PROMPT = """\
You are the Guild Master, an AI orchestrator managing a team of developer heroes (Claude Code agents).

Your responsibilities:
1. Decompose developer goals into actionable quests
2. Assign quests to heroes based on their skills
3. Process hero completion reports
4. Maintain quest chains (impl → test → review → merge)

Quest tiers:
- COMMON: < 30 min, single file changes
- RARE: 1-2 hours, multi-file feature
- EPIC: 2-4 hours, complex feature
- LEGENDARY: full subsystem (decompose into smaller quests)
- BOSS: entire project phase (MUST decompose, never assign directly)

Quest types: feature, bugfix, test, review, chore, refactor, docs

Rules:
- Max 4 hours estimated work per quest
- BOSS tier must be decomposed into EPIC or smaller
- Each quest needs: title, description, tier, type, required skills, branch name
- Branch format: {type}/GLD-{short_id}-{slug}
- No hero holds two roles (impl + review) in the same chain

Respond ONLY with valid JSON in this format:
{
  "analysis": "brief analysis of the goal/situation",
  "actions": [
    {
      "type": "create_chain",
      "goal": "chain goal description",
      "project_id": "project name"
    },
    {
      "type": "create_quest",
      "chain_id": "<will be filled>",
      "title": "quest title",
      "description": "detailed quest description with acceptance criteria",
      "tier": "COMMON|RARE|EPIC",
      "quest_type": "feature|bugfix|test|review|chore|refactor|docs",
      "req_skills": ["skill1", "skill2"],
      "branch": "feature/GLD-xxx-slug"
    },
    {
      "type": "assign",
      "quest_index": 0,
      "hero_name": "hero name"
    }
  ],
  "escalations": ["any issues requiring developer attention"],
  "next": "what happens next"
}
"""


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def log_activity(conn, actor, action, quest_id=None, project_id=None, level="info"):
    conn.execute(
        "INSERT INTO activity_log (id, timestamp, actor, action, quest_id, project_id, level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), datetime.now(timezone.utc).isoformat(), actor, action, quest_id, project_id, level),
    )
    conn.commit()


def get_heroes(conn):
    return conn.execute(
        "SELECT h.id, h.name, h.class, h.status, h.level, h.current_quest_id, "
        "GROUP_CONCAT(s.name, ',') as skills "
        "FROM heroes h LEFT JOIN hero_skills s ON h.id = s.hero_id "
        "GROUP BY h.id"
    ).fetchall()


def get_projects(conn):
    return conn.execute("SELECT * FROM projects WHERE status = 'active'").fetchall()


def read_inbox():
    """Read and clear Guild Master inbox."""
    inbox_file = INBOX / "guild-master.md"
    if not inbox_file.exists():
        return None
    content = inbox_file.read_text().strip()
    if not content:
        return None
    # Clear inbox after reading
    inbox_file.write_text("")
    return content


def read_hero_outboxes():
    """Read completion reports from hero outboxes."""
    reports = []
    for outbox_file in OUTBOX.glob("*.md"):
        if outbox_file.name == "guild-master.md":
            continue
        content = outbox_file.read_text().strip()
        if content and "Quest Complete" in content:
            hero_name = outbox_file.stem
            reports.append({"hero": hero_name, "content": content})
            outbox_file.write_text("")  # Clear after reading
    return reports


def build_context(conn, inbox_content=None, hero_reports=None):
    """Build context message for the Guild Master LLM."""
    heroes = get_heroes(conn)
    projects = get_projects(conn)

    # Active quests
    active_quests = conn.execute(
        "SELECT q.id, q.title, q.tier, q.status, q.project_id, h.name as hero "
        "FROM quests q LEFT JOIN heroes h ON q.assigned_to = h.id "
        "WHERE q.status IN ('active', 'backlog', 'blocked') "
        "ORDER BY q.created_at DESC LIMIT 20"
    ).fetchall()

    ctx = "## Current State\n\n"

    ctx += "### Heroes\n"
    for h in heroes:
        skills = h["skills"] or "none"
        ctx += f"- {h['name']} ({h['class']}) — status: {h['status']}, level: {h['level']}, skills: [{skills}]\n"
    if not heroes:
        ctx += "- No heroes recruited\n"

    ctx += "\n### Projects\n"
    for p in projects:
        ctx += f"- {p['name']} ({p['language'] or 'unknown'}) — path: {p['path']}\n"
    if not projects:
        ctx += "- No projects registered\n"

    ctx += "\n### Active Quests\n"
    for q in active_quests:
        hero = q["hero"] or "unassigned"
        ctx += f"- [{q['id'][:8]}] {q['title']} ({q['tier']}, {q['status']}) → {hero}\n"
    if not active_quests:
        ctx += "- No active quests\n"

    if inbox_content:
        ctx += f"\n### New Goal from Developer\n{inbox_content}\n"

    if hero_reports:
        ctx += "\n### Hero Completion Reports\n"
        for report in hero_reports:
            ctx += f"\n#### {report['hero']}\n{report['content']}\n"

    return ctx


def process_actions(conn, response_data):
    """Process Guild Master's action list."""
    actions = response_data.get("actions", [])
    created_quests = []
    current_chain_id = None

    for action in actions:
        action_type = action.get("type")

        if action_type == "create_chain":
            chain_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            project_id = action.get("project_id", "")

            # Resolve project ID from name
            row = conn.execute("SELECT id FROM projects WHERE name = ?", (project_id,)).fetchone()
            if row:
                project_id = row["id"]

            conn.execute(
                "INSERT INTO quest_chains (id, goal, project_id, status, created_at) VALUES (?, ?, ?, 'active', ?)",
                (chain_id, action.get("goal", ""), project_id, now),
            )
            current_chain_id = chain_id
            log_activity(conn, "guild-master", f"Created quest chain: {action.get('goal', '')}", project_id=project_id)
            print(f"  + Chain: {action.get('goal', '')}")

        elif action_type == "create_quest":
            chain_id = action.get("chain_id") or current_chain_id
            if not chain_id:
                print(f"  ! Skipping quest (no chain): {action.get('title')}")
                continue

            quest_id = f"GLD-{uuid.uuid4().hex[:6].upper()}"
            now = datetime.now(timezone.utc).isoformat()
            branch = action.get("branch", f"{action.get('quest_type', 'feature')}/GLD-{quest_id[-6:]}-quest")

            # Get project_id from chain
            chain_row = conn.execute("SELECT project_id FROM quest_chains WHERE id = ?", (chain_id,)).fetchone()
            project_id = chain_row["project_id"] if chain_row else ""

            conn.execute(
                "INSERT INTO quests (id, chain_id, title, description, tier, type, status, project_id, branch, req_skills, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'backlog', ?, ?, ?, ?)",
                (
                    quest_id, chain_id,
                    action.get("title", ""),
                    action.get("description", ""),
                    action.get("tier", "COMMON"),
                    action.get("quest_type", "feature"),
                    project_id,
                    branch,
                    json.dumps(action.get("req_skills", [])),
                    now,
                ),
            )
            created_quests.append({"id": quest_id, "title": action.get("title", "")})
            log_activity(conn, "guild-master", f"Created quest: {action.get('title', '')}", quest_id=quest_id, project_id=project_id)
            print(f"  + Quest [{quest_id}]: {action.get('title', '')}")

        elif action_type == "assign":
            quest_idx = action.get("quest_index", 0)
            hero_name = action.get("hero_name")

            if quest_idx >= len(created_quests) or not hero_name:
                continue

            quest_id = created_quests[quest_idx]["id"]

            hero_row = conn.execute("SELECT id FROM heroes WHERE name = ?", (hero_name,)).fetchone()
            if not hero_row:
                print(f"  ! Hero '{hero_name}' not found, skipping assignment")
                continue

            hero_id = hero_row["id"]
            conn.execute("UPDATE quests SET assigned_to = ?, status = 'active' WHERE id = ?", (hero_id, quest_id))
            conn.execute("UPDATE heroes SET status = 'on_quest', current_quest_id = ? WHERE id = ?", (quest_id, hero_id))

            # Write quest brief to hero inbox
            quest_row = conn.execute("SELECT * FROM quests WHERE id = ?", (quest_id,)).fetchone()
            if quest_row:
                brief = f"## Quest: {quest_row['title']}\n"
                brief += f"ID: {quest_id}\n"
                brief += f"Branch: {quest_row['branch']}\n"
                brief += f"Tier: {quest_row['tier']} | Type: {quest_row['type']}\n\n"
                brief += f"{quest_row['description']}\n"
                hero_inbox = INBOX / f"{hero_name}.md"
                hero_inbox.write_text(brief)

            log_activity(conn, "guild-master", f"Assigned quest {quest_id} to {hero_name}", quest_id=quest_id)
            print(f"  → Assigned [{quest_id}] to {hero_name}")

    conn.commit()

    # Write GM report
    report = f"# Guild Master Report\n"
    report += f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
    report += f"## Analysis\n{response_data.get('analysis', 'N/A')}\n\n"
    if response_data.get("escalations"):
        report += "## Escalations\n"
        for e in response_data["escalations"]:
            report += f"- {e}\n"
        report += "\n"
    report += f"## Next\n{response_data.get('next', 'Monitoring...')}\n"

    gm_outbox = OUTBOX / "guild-master.md"
    gm_outbox.write_text(report)


def process_hero_report(conn, hero_name, content):
    """Process a hero's quest completion report."""
    # Parse quest ID from report
    match = re.search(r"Quest Complete:\s*(GLD-\w+)", content)
    if not match:
        print(f"  ! Could not parse quest ID from {hero_name}'s report")
        return

    quest_id = match.group(1)
    now = datetime.now(timezone.utc).isoformat()

    # Check status
    is_blocked = "Status: blocked" in content.lower() or "status: blocked" in content

    if is_blocked:
        conn.execute("UPDATE quests SET status = 'blocked' WHERE id = ?", (quest_id,))
        conn.execute("UPDATE heroes SET status = 'blocked' WHERE name = ?", (hero_name,))
        log_activity(conn, hero_name, f"Quest {quest_id} blocked", quest_id=quest_id, level="warning")
        print(f"  ! {hero_name}: quest {quest_id} blocked")
    else:
        conn.execute("UPDATE quests SET status = 'done', completed_at = ? WHERE id = ?", (now, quest_id))
        conn.execute("UPDATE heroes SET status = 'idle', current_quest_id = NULL WHERE name = ?", (hero_name,))

        # XP reward based on tier
        quest = conn.execute("SELECT tier FROM quests WHERE id = ?", (quest_id,)).fetchone()
        xp_map = {"COMMON": 10, "RARE": 25, "EPIC": 50, "LEGENDARY": 100}
        xp = xp_map.get(quest["tier"], 10) if quest else 10
        conn.execute("UPDATE heroes SET xp = xp + ? WHERE name = ?", (xp, hero_name))

        # Level up check
        hero = conn.execute("SELECT xp, level FROM heroes WHERE name = ?", (hero_name,)).fetchone()
        if hero:
            new_level = 1 + hero["xp"] // 100
            if new_level > hero["level"]:
                conn.execute("UPDATE heroes SET level = ? WHERE name = ?", (new_level, hero_name))
                log_activity(conn, hero_name, f"Leveled up to {new_level}!", level="info")
                print(f"  ★ {hero_name} leveled up to {new_level}!")

        log_activity(conn, hero_name, f"Quest {quest_id} completed (+{xp} XP)", quest_id=quest_id)
        print(f"  ✓ {hero_name}: quest {quest_id} completed (+{xp} XP)")

    # Save learnings to hero history
    hero_dir = GUILD_DIR / "workspace" / "memory" / "heroes" / hero_name
    history_file = hero_dir / "history.md"
    if history_file.exists():
        history = history_file.read_text()
        history += f"\n## {quest_id} — {now[:10]}\n{content}\n"
        history_file.write_text(history)

    conn.commit()


def call_guild_master(client, context):
    """Call Claude API for Guild Master decisions."""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )

    text = response.content[0].text

    # Extract JSON from response
    json_match = re.search(r'\{[\s\S]*\}', text)
    if not json_match:
        print(f"  ! Guild Master response was not valid JSON")
        return None

    try:
        return json.loads(json_match.group())
    except json.JSONDecodeError as e:
        print(f"  ! Failed to parse Guild Master response: {e}")
        return None


def run_cycle(client):
    """Run one Guild Master cycle."""
    conn = get_db()

    # Check for new goals
    inbox_content = read_inbox()

    # Check for hero reports
    hero_reports = read_hero_outboxes()

    # Process hero reports directly (no LLM needed)
    for report in hero_reports:
        process_hero_report(conn, report["hero"], report["content"])

    # If there's a new goal, call LLM to decompose
    if inbox_content:
        print(f"\n📜 New goal received")
        context = build_context(conn, inbox_content=inbox_content)
        response_data = call_guild_master(client, context)
        if response_data:
            print(f"  Analysis: {response_data.get('analysis', 'N/A')}")
            process_actions(conn, response_data)

    conn.close()


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        return

    if not DB_PATH.exists():
        print("Error: Guild not initialized. Run 'guild init' first.")
        return

    client = anthropic.Anthropic(api_key=api_key)

    print("⚔ Guild Master online")
    print(f"  Polling every {POLL_INTERVAL}s")
    print(f"  Inbox: {INBOX}")
    print(f"  Press Ctrl+C to stop\n")

    log_activity(get_db(), "guild-master", "Guild Master started")

    try:
        while True:
            try:
                run_cycle(client)
            except Exception as e:
                print(f"  ! Cycle error: {e}")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n⚔ Guild Master offline")
        log_activity(get_db(), "guild-master", "Guild Master stopped")


if __name__ == "__main__":
    main()
