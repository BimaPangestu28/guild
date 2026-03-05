#!/usr/bin/env python3
"""
Guild Master — orchestrator agent for the Guild system.

Watches inbox for new goals, decomposes them into quest chains,
assigns quests to heroes, and processes hero completion reports.
"""

import json
import os
import re
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from memory_manager import read_shared_memory, route_learnings, update_proficiency


# ---------------------------------------------------------------------------
# Cost tracking — session-level API call counter
# ---------------------------------------------------------------------------
_session_api_calls = 0
_session_token_total = 0

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

        # Resolve project name for memory operations
        quest_detail = conn.execute("SELECT project_id FROM quests WHERE id = ?", (quest_id,)).fetchone()
        project_name = None
        if quest_detail and quest_detail["project_id"]:
            project_row = conn.execute(
                "SELECT name FROM projects WHERE id = ?", (quest_detail["project_id"],)
            ).fetchone()
            if project_row:
                project_name = project_row["name"]

        # Route learnings from report if present
        if project_name:
            learnings_match = re.search(r"(?:Learnings|Notes|Insights):\s*\n([\s\S]+?)(?:\n##|\Z)", content)
            if learnings_match:
                route_learnings(hero_name, quest_id, learnings_match.group(1).strip(), project_name)

        # Update proficiency tracking
        if project_name:
            hero_row = conn.execute("SELECT id FROM heroes WHERE name = ?", (hero_name,)).fetchone()
            if hero_row:
                update_proficiency(hero_row["id"], project_name)

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
    global _session_api_calls, _session_token_total

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )

    # Track cost
    _session_api_calls += 1
    tokens_used = getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0)
    _session_token_total += tokens_used
    try:
        conn = get_db()
        log_cost(conn, "guild-master", tokens_used)
        conn.close()
    except Exception:
        pass  # Don't let cost logging break the main flow

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


def log_cost(conn, actor, tokens, quest_id=None):
    """Log estimated token usage to activity_log."""
    log_activity(conn, actor, f"api_cost: {tokens} tokens", quest_id=quest_id)


def find_best_hero(conn, req_skills, exclude_hero_ids=None):
    """Find the best available hero matching required skills.

    Considers heroes with status in ('idle', 'offline') that have no current quest.
    Scores each by skill overlap with *req_skills*.
    Returns the hero Row with the best match, or None.
    """
    if exclude_hero_ids is None:
        exclude_hero_ids = set()
    else:
        exclude_hero_ids = set(exclude_hero_ids)

    heroes = conn.execute(
        "SELECT h.id, h.name, h.class, h.status, h.level, h.current_quest_id, "
        "GROUP_CONCAT(s.name, ',') as skills "
        "FROM heroes h LEFT JOIN hero_skills s ON h.id = s.hero_id "
        "WHERE h.status IN ('idle', 'offline') AND h.current_quest_id IS NULL "
        "GROUP BY h.id"
    ).fetchall()

    req_set = set(s.lower() for s in req_skills) if req_skills else set()
    best = None
    best_score = -1

    for hero in heroes:
        if hero["id"] in exclude_hero_ids:
            continue
        hero_skills = set(
            s.strip().lower() for s in (hero["skills"] or "").split(",") if s.strip()
        )
        score = len(req_set & hero_skills) if req_set else 0
        if score > best_score:
            best_score = score
            best = hero

    return best


# ---------------------------------------------------------------------------
# Quest chain automation helpers
# ---------------------------------------------------------------------------

_CHAIN_SEQUENCE = {"feature": "test", "bugfix": "test", "test": "review", "refactor": "test"}


def _get_chain_hero_ids(conn, chain_id):
    """Return set of hero IDs already assigned to quests in a chain."""
    rows = conn.execute(
        "SELECT DISTINCT assigned_to FROM quests WHERE chain_id = ? AND assigned_to IS NOT NULL",
        (chain_id,),
    ).fetchall()
    return {r["assigned_to"] for r in rows}


def _auto_create_next_quest(conn, completed_quest, client):
    """If the completed quest is part of a sequence, create the next quest in the chain."""
    quest_type = completed_quest["type"]
    next_type = _CHAIN_SEQUENCE.get(quest_type)
    if not next_type:
        # review completed (or other terminal type) → mark chain done
        if quest_type == "review":
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE quest_chains SET status = 'done', completed_at = ? WHERE id = ?",
                (now, completed_quest["chain_id"]),
            )
            log_activity(conn, "guild-master", f"Chain {completed_quest['chain_id'][:8]} completed",
                         project_id=completed_quest["project_id"])
            print(f"  >> Chain {completed_quest['chain_id'][:8]} completed")
            conn.commit()
        return

    chain_id = completed_quest["chain_id"]
    exclude_ids = _get_chain_hero_ids(conn, chain_id)

    req_skills = json.loads(completed_quest["req_skills"]) if completed_quest["req_skills"] else []
    hero = find_best_hero(conn, req_skills, exclude_hero_ids=exclude_ids)

    quest_id = f"GLD-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    title = f"[{next_type}] {completed_quest['title']}"
    description = (
        f"Auto-generated {next_type} quest following completion of {completed_quest['id']}.\n\n"
        f"Original quest: {completed_quest['title']}\n"
        f"Branch: {completed_quest['branch']}\n"
    )
    branch = f"{next_type}/{quest_id[-6:]}-{completed_quest['branch'].split('/')[-1] if '/' in completed_quest['branch'] else completed_quest['branch']}"

    conn.execute(
        "INSERT INTO quests (id, chain_id, parent_quest_id, title, description, tier, type, status, "
        "project_id, branch, req_skills, assigned_to, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            quest_id, chain_id, completed_quest["id"],
            title, description,
            completed_quest["tier"], next_type,
            "active" if hero else "backlog",
            completed_quest["project_id"],
            branch,
            completed_quest["req_skills"],
            hero["id"] if hero else None,
            now,
        ),
    )

    log_activity(conn, "guild-master",
                 f"Auto-created {next_type} quest {quest_id} in chain {chain_id[:8]}",
                 quest_id=quest_id, project_id=completed_quest["project_id"])
    print(f"  >> Auto-created [{quest_id}] {next_type} quest in chain {chain_id[:8]}")

    if hero:
        conn.execute(
            "UPDATE heroes SET status = 'on_quest', current_quest_id = ? WHERE id = ?",
            (quest_id, hero["id"]),
        )
        # Write quest brief to hero inbox
        brief = f"## Quest: {title}\nID: {quest_id}\nBranch: {branch}\n"
        brief += f"Tier: {completed_quest['tier']} | Type: {next_type}\n\n{description}\n"
        hero_inbox = INBOX / f"{hero['name']}.md"
        hero_inbox.write_text(brief)
        log_activity(conn, "guild-master", f"Assigned chain quest {quest_id} to {hero['name']}", quest_id=quest_id)
        print(f"  -> Assigned [{quest_id}] to {hero['name']}")

    conn.commit()


# ---------------------------------------------------------------------------
# Auto-assign idle heroes to backlog quests
# ---------------------------------------------------------------------------

def _auto_assign_idle_heroes(conn):
    """Match idle heroes to unassigned backlog quests by skill overlap."""
    backlog_quests = conn.execute(
        "SELECT * FROM quests WHERE status = 'backlog' AND assigned_to IS NULL "
        "ORDER BY created_at ASC"
    ).fetchall()

    if not backlog_quests:
        return

    for quest in backlog_quests:
        req_skills = json.loads(quest["req_skills"]) if quest["req_skills"] else []
        hero = find_best_hero(conn, req_skills)
        if not hero:
            continue

        conn.execute("UPDATE quests SET assigned_to = ?, status = 'active' WHERE id = ?",
                     (hero["id"], quest["id"]))
        conn.execute("UPDATE heroes SET status = 'on_quest', current_quest_id = ? WHERE id = ?",
                     (quest["id"], hero["id"]))

        # Write quest brief
        brief = f"## Quest: {quest['title']}\nID: {quest['id']}\nBranch: {quest['branch']}\n"
        brief += f"Tier: {quest['tier']} | Type: {quest['type']}\n\n{quest['description']}\n"
        hero_inbox = INBOX / f"{hero['name']}.md"
        hero_inbox.write_text(brief)

        log_activity(conn, "guild-master",
                     f"Auto-assigned quest {quest['id']} to {hero['name']} (skill match)",
                     quest_id=quest["id"], project_id=quest["project_id"])
        print(f"  -> Auto-assigned [{quest['id']}] to {hero['name']}")

    conn.commit()


# ---------------------------------------------------------------------------
# Blocked quest handling
# ---------------------------------------------------------------------------

def _get_block_count(conn, quest_id):
    """Count how many times a quest has been blocked (via activity_log)."""
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM activity_log "
        "WHERE quest_id = ? AND action LIKE '%blocked%' AND level = 'warning'",
        (quest_id,),
    ).fetchone()
    return row["cnt"] if row else 0


def _handle_blocked_quests(conn, client):
    """Handle blocked quests with escalating strategies."""
    blocked = conn.execute(
        "SELECT q.*, h.name as hero_name, h.id as hero_id "
        "FROM quests q LEFT JOIN heroes h ON q.assigned_to = h.id "
        "WHERE q.status = 'blocked'"
    ).fetchall()

    for quest in blocked:
        block_count = _get_block_count(conn, quest["id"])

        if block_count <= 1:
            # First block: enrich with shared memory context, reassign
            project_row = conn.execute(
                "SELECT name FROM projects WHERE id = ?", (quest["project_id"],)
            ).fetchone()
            extra_context = ""
            if project_row:
                shared = read_shared_memory(project_row["name"])
                if shared:
                    extra_context = f"\n\n--- Shared Memory Context ---\n{shared[:2000]}"

            if extra_context:
                new_desc = quest["description"] + extra_context
                conn.execute("UPDATE quests SET description = ?, status = 'active' WHERE id = ?",
                             (new_desc, quest["id"]))
                log_activity(conn, "guild-master",
                             f"Unblocked quest {quest['id']} with shared memory context",
                             quest_id=quest["id"], level="info")
                print(f"  >> Enriched blocked quest [{quest['id']}] with shared memory")
            else:
                # No shared memory available, just reset to active
                conn.execute("UPDATE quests SET status = 'active' WHERE id = ?", (quest["id"],))
                log_activity(conn, "guild-master",
                             f"Reset blocked quest {quest['id']} to active (no extra context available)",
                             quest_id=quest["id"], level="info")

        elif block_count == 2:
            # Second block: decompose into sub-quests via LLM
            decompose_prompt = (
                f"A quest is blocked for the second time. Decompose it into 2-3 smaller sub-quests.\n\n"
                f"Quest: {quest['title']}\nDescription: {quest['description']}\n"
                f"Tier: {quest['tier']} | Type: {quest['type']}\n\n"
                f"Respond with JSON: {{\"sub_quests\": [{{\"title\": ..., \"description\": ..., "
                f"\"tier\": \"COMMON\", \"quest_type\": \"{quest['type']}\", "
                f"\"req_skills\": [...]}}]}}"
            )
            result = call_guild_master(client, decompose_prompt)
            if result and "sub_quests" in result:
                for sq in result["sub_quests"]:
                    sub_id = f"GLD-{uuid.uuid4().hex[:6].upper()}"
                    now = datetime.now(timezone.utc).isoformat()
                    branch = f"{sq.get('quest_type', quest['type'])}/{sub_id[-6:]}-sub"
                    conn.execute(
                        "INSERT INTO quests (id, chain_id, parent_quest_id, title, description, tier, type, "
                        "status, project_id, branch, req_skills, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, 'backlog', ?, ?, ?, ?)",
                        (
                            sub_id, quest["chain_id"], quest["id"],
                            sq.get("title", "Sub-quest"),
                            sq.get("description", ""),
                            sq.get("tier", "COMMON"),
                            sq.get("quest_type", quest["type"]),
                            quest["project_id"], branch,
                            json.dumps(sq.get("req_skills", [])),
                            now,
                        ),
                    )
                    log_activity(conn, "guild-master",
                                 f"Decomposed blocked quest {quest['id']} -> sub-quest {sub_id}",
                                 quest_id=sub_id, project_id=quest["project_id"])
                    print(f"  >> Decomposed [{quest['id']}] -> sub-quest [{sub_id}]")

                # Mark original as superseded
                conn.execute("UPDATE quests SET status = 'done', result = 'decomposed' WHERE id = ?",
                             (quest["id"],))
                if quest["hero_id"]:
                    conn.execute(
                        "UPDATE heroes SET status = 'idle', current_quest_id = NULL WHERE id = ?",
                        (quest["hero_id"],),
                    )

        else:
            # Third+ block: escalate
            log_activity(conn, "guild-master",
                         f"ESCALATION: Quest {quest['id']} blocked {block_count} times — requires manual intervention",
                         quest_id=quest["id"], project_id=quest["project_id"], level="critical")
            print(f"  !! ESCALATION: [{quest['id']}] blocked {block_count} times")
            # Write to GM outbox for developer attention
            gm_outbox = OUTBOX / "guild-master.md"
            escalation_msg = (
                f"\n\n## ESCALATION — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
                f"Quest [{quest['id']}] \"{quest['title']}\" has been blocked {block_count} times.\n"
                f"Assigned to: {quest['hero_name'] or 'unassigned'}\n"
                f"Manual intervention required.\n"
            )
            existing = gm_outbox.read_text() if gm_outbox.exists() else ""
            gm_outbox.write_text(existing + escalation_msg)

    conn.commit()


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

    # Quest chain automation: check for newly completed quests that are part of a chain
    completed_quests = conn.execute(
        "SELECT * FROM quests WHERE status = 'done' AND completed_at IS NOT NULL "
        "AND chain_id IS NOT NULL AND type IN ('feature', 'bugfix', 'test', 'review', 'refactor')"
    ).fetchall()
    for cq in completed_quests:
        # Only process if no successor quest already exists for this quest
        existing_next = conn.execute(
            "SELECT id FROM quests WHERE parent_quest_id = ?", (cq["id"],)
        ).fetchone()
        if not existing_next:
            _auto_create_next_quest(conn, cq, client)

    # If there's a new goal, call LLM to decompose
    if inbox_content:
        print(f"\n📜 New goal received")
        context = build_context(conn, inbox_content=inbox_content)
        response_data = call_guild_master(client, context)
        if response_data:
            print(f"  Analysis: {response_data.get('analysis', 'N/A')}")
            process_actions(conn, response_data)

    # Auto-assign idle heroes to unassigned backlog quests
    _auto_assign_idle_heroes(conn)

    # Handle blocked quests (escalating strategy)
    _handle_blocked_quests(conn, client)

    conn.close()


def db_backup():
    """Create hourly database backup."""
    backup_dir = GUILD_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_name = f"guild-{timestamp}.db"
    shutil.copy2(str(DB_PATH), str(backup_dir / backup_name))

    # Retain only last 24
    backups = sorted(backup_dir.glob("guild-*.db"))
    while len(backups) > 24:
        backups[0].unlink()
        backups.pop(0)

    print(f"  Auto-backup: {backup_name}")


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

    last_backup = time.time()

    try:
        while True:
            try:
                run_cycle(client)
            except Exception as e:
                print(f"  ! Cycle error: {e}")

            # Hourly auto-backup
            if time.time() - last_backup > 3600:
                try:
                    db_backup()
                except Exception as e:
                    print(f"  ! Backup error: {e}")
                last_backup = time.time()

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n⚔ Guild Master offline")
        log_activity(get_db(), "guild-master", "Guild Master stopped")


if __name__ == "__main__":
    main()
