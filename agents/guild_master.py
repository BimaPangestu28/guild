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
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic

from memory_manager import clear_quest_context, read_shared_memory, route_learnings, update_proficiency


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

MAX_CONSECUTIVE_CRASHES = 3
CRASH_WINDOW_SECONDS = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Error handling levels
# ---------------------------------------------------------------------------

class GuildError:
    FATAL = "fatal"
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


def _load_telegram_bot():
    try:
        from telegram_bot import TelegramBot
        bot = TelegramBot()
        if bot.token and bot.chat_id:
            return bot
    except Exception:
        pass
    return None


def handle_error(level, message, context=None):
    try:
        conn = get_db()
        log_activity(conn, "guild-master", f"[{level.upper()}] {message}")
        conn.close()
    except Exception:
        print(f"  ! Could not log error: [{level.upper()}] {message}")

    if level == GuildError.FATAL:
        bot = _load_telegram_bot()
        if bot:
            bot.send_notification(4, f"FATAL: {message}")
        pause_all_heroes()
        raise SystemExit(f"FATAL: {message}")

    elif level == GuildError.CRITICAL:
        bot = _load_telegram_bot()
        if bot:
            bot.send_notification(4, f"CRITICAL: {message}")

    elif level == GuildError.WARNING:
        bot = _load_telegram_bot()
        if bot:
            bot.send_notification(3, f"WARNING: {message}")


def pause_all_heroes():
    try:
        conn = get_db()
        conn.execute("UPDATE heroes SET status = 'offline' WHERE status IN ('idle', 'on_quest')")
        conn.commit()
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Safe DB wrapper with corruption detection
# ---------------------------------------------------------------------------

def safe_db_execute(conn, query, params=None, fetch=None):
    try:
        if params:
            cursor = conn.execute(query, params)
        else:
            cursor = conn.execute(query)
        if fetch == "one":
            return cursor.fetchone()
        elif fetch == "all":
            return cursor.fetchall()
        return cursor
    except sqlite3.DatabaseError as e:
        error_msg = str(e)
        if "malformed" in error_msg or "corrupt" in error_msg or "disk" in error_msg:
            _handle_db_corruption(error_msg)
        raise


def _handle_db_corruption(error_msg):
    backup_dir = GUILD_DIR / "backups"
    backups = sorted(backup_dir.glob("guild-*.db")) if backup_dir.exists() else []

    if backups:
        latest_backup = backups[-1]
        try:
            corrupt_path = DB_PATH.with_suffix(".db.corrupt")
            if DB_PATH.exists():
                shutil.move(str(DB_PATH), str(corrupt_path))
            shutil.copy2(str(latest_backup), str(DB_PATH))
            handle_error(GuildError.CRITICAL, f"DB corruption detected: {error_msg}. Restored from {latest_backup.name}")
            return
        except Exception as restore_err:
            handle_error(GuildError.FATAL, f"DB corruption detected and restore failed: {restore_err}")
    else:
        handle_error(GuildError.FATAL, f"DB corruption detected: {error_msg}. No backups available for restore.")

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

IMPORTANT:
- BOSS tier quests must always be decomposed into smaller quests. Never create a single BOSS quest.
- Each quest should represent at most 4 hours of work. If larger, decompose into multiple quests.

Quest types: feature, bugfix, test, review, fix, chore, refactor, docs

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


def _enforce_quest_rules(conn, quests_data):
    """Enforce quest creation rules before inserting."""
    for quest in quests_data:
        # Boss tier must be decomposed, never assigned directly
        if quest.get("tier") == "BOSS":
            # Don't create BOSS quests directly - they should be decomposed further
            log_activity(conn, "guild-master",
                f"BOSS tier quest rejected — must be decomposed: {quest.get('title', 'untitled')}")
            continue

        # Max 4h estimated work per quest - if description suggests large scope, split
        yield quest


def process_actions(conn, response_data):
    """Process Guild Master's action list."""
    actions = response_data.get("actions", [])
    created_quests = []
    current_chain_id = None

    # Filter quest actions through enforcement rules
    quest_actions = [a for a in actions if a.get("type") == "create_quest"]
    enforced_quests = set()
    for idx, q in enumerate(quest_actions):
        for _ in _enforce_quest_rules(conn, [q]):
            enforced_quests.add(id(q))

    for action in actions:
        action_type = action.get("type")

        if action_type == "create_quest" and id(action) not in enforced_quests:
            print(f"  ! Skipping BOSS tier quest: {action.get('title')}")
            created_quests.append(None)  # placeholder to keep indices aligned
            continue

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

            if created_quests[quest_idx] is None:
                print(f"  ! Skipping assignment — quest at index {quest_idx} was rejected by enforcement rules")
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

        # Send each escalation via Telegram
        try:
            _tg_bot = _load_telegram_bot()
            if _tg_bot:
                for e in response_data["escalations"]:
                    _tg_bot.notify_escalation("guild-master", e)
        except Exception:
            pass

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

        # Send formatted Telegram notifications for quest completion and level-up
        try:
            _tg_bot = _load_telegram_bot()
            if _tg_bot:
                _q_row = conn.execute(
                    "SELECT title, chain_id FROM quests WHERE id = ?", (quest_id,)
                ).fetchone()
                _q_title = _q_row["title"] if _q_row else quest_id
                _q_chain = _q_row["chain_id"] if _q_row else None
                _tg_bot.notify_quest_complete(quest_id, _q_title, hero_name, chain_id=_q_chain)

                if hero and new_level > hero["level"]:
                    _h_detail = conn.execute(
                        "SELECT class FROM heroes WHERE name = ?", (hero_name,)
                    ).fetchone()
                    _h_class = _h_detail["class"] if _h_detail else "Unknown"
                    _tg_bot.notify_level_up(hero_name, _h_class, new_level)
        except Exception:
            pass

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

        # Clear quest context from hero's CLAUDE.md after completion
        clear_quest_context(hero_name)

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

    if not check_cost_cap():
        print("  ! Skipping API call — daily cost cap exceeded")
        return None

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )

    _session_api_calls += 1
    input_tokens = getattr(response.usage, "input_tokens", 0)
    output_tokens = getattr(response.usage, "output_tokens", 0)
    _session_token_total += input_tokens + output_tokens
    cost = (input_tokens * 3.0 / 1_000_000) + (output_tokens * 15.0 / 1_000_000)
    try:
        log_cost_to_db("guild-master", input_tokens, output_tokens, cost, "claude-sonnet-4-20250514")
    except Exception:
        pass

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


def log_cost_to_db(actor, input_tokens, output_tokens, cost, model="claude-sonnet-4-20250514", quest_id=None, project_id=None):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO cost_log (id, actor, category, project_id, quest_id, input_tokens, output_tokens, cost_usd, model) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), actor, "guild_master", project_id, quest_id, input_tokens, output_tokens, cost, model),
    )
    conn.commit()
    conn.close()


def get_daily_cost():
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_log WHERE date(timestamp) = date('now')"
    ).fetchone()
    conn.close()
    return row[0] if row else 0.0


def get_cost_cap():
    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute("SELECT value FROM config WHERE key = 'cost-cap-daily'").fetchone()
    except Exception:
        conn.close()
        return 10.0
    conn.close()
    if row:
        try:
            return float(row[0])
        except (ValueError, TypeError):
            pass
    return 10.0


def check_cost_cap():
    daily_cost = get_daily_cost()
    cap = get_cost_cap()
    percentage = (daily_cost / cap * 100) if cap > 0 else 0

    # Send warning at 80% threshold even if not exceeded
    if percentage >= 80:
        try:
            _tg_bot = _load_telegram_bot()
            if _tg_bot:
                _tg_bot.notify_cost_warning(daily_cost, cap, percentage)
        except Exception:
            pass

    if daily_cost >= cap:
        print(f"  !! COST CAP EXCEEDED: ${daily_cost:.2f} >= ${cap:.2f}")
        conn = get_db()
        log_activity(conn, "guild-master", f"Cost cap exceeded: ${daily_cost:.2f} >= ${cap:.2f}", level="critical")
        conn.execute("UPDATE heroes SET status = 'paused' WHERE status IN ('idle', 'on_quest')")
        conn.commit()
        log_activity(conn, "guild-master", "All heroes paused due to cost cap", level="warning")
        conn.close()
        return False
    return True


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

_CHAIN_SEQUENCE = {"feature": "test", "bugfix": "test", "test": "review", "refactor": "test", "fix": "review"}

MAX_REVIEW_CYCLES = 3


def _get_chain_hero_ids(conn, chain_id):
    """Return set of hero IDs already assigned to quests in a chain."""
    rows = conn.execute(
        "SELECT DISTINCT assigned_to FROM quests WHERE chain_id = ? AND assigned_to IS NOT NULL",
        (chain_id,),
    ).fetchall()
    return {r["assigned_to"] for r in rows}


def _get_review_cycle_count(conn, chain_id):
    """Count how many review quests exist in a chain (indicates review cycles)."""
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM quests WHERE chain_id = ? AND type = 'review'",
        (chain_id,),
    ).fetchone()
    return row["cnt"] if row else 0


def _get_original_implementor(conn, chain_id):
    """Find the hero assigned to the first quest in the chain (the original implementor)."""
    row = conn.execute(
        "SELECT assigned_to FROM quests WHERE chain_id = ? ORDER BY created_at ASC LIMIT 1",
        (chain_id,),
    ).fetchone()
    if row and row["assigned_to"]:
        return conn.execute("SELECT * FROM heroes WHERE id = ?", (row["assigned_to"],)).fetchone()
    return None


def _should_skip_chain(quest):
    """COMMON tier quests skip test/review steps."""
    return quest["tier"] == "COMMON"


def _auto_create_next_quest(conn, completed_quest, client):
    """If the completed quest is part of a sequence, create the next quest in the chain."""
    quest_type = completed_quest["type"]

    if _should_skip_chain(completed_quest) and quest_type in ("feature", "bugfix", "fix"):
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE quest_chains SET status = 'done', completed_at = ? WHERE id = ?",
            (now, completed_quest["chain_id"]),
        )
        log_activity(conn, "guild-master",
                     f"Chain {completed_quest['chain_id'][:8]} completed (COMMON tier, skipped test/review)",
                     project_id=completed_quest["project_id"])
        print(f"  >> Chain {completed_quest['chain_id'][:8]} completed (COMMON, skipped test/review)")
        check_merge_ready(conn, completed_quest["chain_id"])
        conn.commit()
        return

    next_type = _CHAIN_SEQUENCE.get(quest_type)
    if not next_type:
        # review completed (or other terminal type) → check for changes_requested or mark chain done
        if quest_type == "review":
            changes_requested = _check_changes_requested(conn, completed_quest)
            if changes_requested:
                _create_fix_quest(conn, completed_quest)
                return

            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE quest_chains SET status = 'done', completed_at = ? WHERE id = ?",
                (now, completed_quest["chain_id"]),
            )
            log_activity(conn, "guild-master", f"Chain {completed_quest['chain_id'][:8]} completed",
                         project_id=completed_quest["project_id"])
            print(f"  >> Chain {completed_quest['chain_id'][:8]} completed")

            check_merge_ready(conn, completed_quest["chain_id"])
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


def _check_changes_requested(conn, review_quest):
    """Check if a review quest resulted in changes_requested status."""
    hero_name = None
    if review_quest["assigned_to"]:
        hero_row = conn.execute(
            "SELECT name FROM heroes WHERE id = ?", (review_quest["assigned_to"],)
        ).fetchone()
        if hero_row:
            hero_name = hero_row["name"]

    if not hero_name:
        return False

    history_file = GUILD_DIR / "workspace" / "memory" / "heroes" / hero_name / "history.md"
    if not history_file.exists():
        return False

    history = history_file.read_text()
    quest_pattern = rf"## {re.escape(review_quest['id'])}.*?\n([\s\S]*?)(?=\n## |\Z)"
    match = re.search(quest_pattern, history)
    if match:
        report_text = match.group(1).lower()
        if "changes_requested" in report_text or "changes requested" in report_text:
            return True

    rows = conn.execute(
        "SELECT action FROM activity_log WHERE quest_id = ? AND action LIKE '%changes_requested%'",
        (review_quest["id"],),
    ).fetchall()
    return len(rows) > 0


def _create_fix_quest(conn, review_quest):
    """Create a fix quest after a review with changes_requested."""
    chain_id = review_quest["chain_id"]

    review_cycles = _get_review_cycle_count(conn, chain_id)
    if review_cycles >= MAX_REVIEW_CYCLES:
        log_activity(
            conn, "guild-master",
            f"ESCALATION: Chain {chain_id[:8]} hit {review_cycles} review cycles — requires developer intervention",
            project_id=review_quest["project_id"], level="critical",
        )
        print(f"  !! ESCALATION: Chain {chain_id[:8]} exceeded max review cycles ({review_cycles})")
        gm_outbox = OUTBOX / "guild-master.md"
        escalation_msg = (
            f"\n\n## ESCALATION — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"Chain {chain_id[:8]} has gone through {review_cycles} review cycles.\n"
            f"Max review cycles ({MAX_REVIEW_CYCLES}) exceeded. Developer intervention required.\n"
        )
        existing = gm_outbox.read_text() if gm_outbox.exists() else ""
        gm_outbox.write_text(existing + escalation_msg)

        # Send formatted Telegram escalation for review cycle limit
        try:
            _tg_bot = _load_telegram_bot()
            if _tg_bot:
                _problem = f"Chain {chain_id[:8]} exceeded {review_cycles} review cycles (max {MAX_REVIEW_CYCLES})"
                _tg_bot.notify_escalation(chain_id[:8], _problem, options=["Merge as-is", "Abandon chain"])
        except Exception:
            pass

        conn.commit()
        return

    original_implementor = _get_original_implementor(conn, chain_id)
    original_title = review_quest["title"]
    if original_title.startswith("[review] "):
        original_title = original_title[len("[review] "):]
    if original_title.startswith("[fix] "):
        original_title = original_title[len("[fix] "):]

    review_feedback = review_quest.get("result") or review_quest["description"]
    quest_id = f"GLD-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    title = f"Address review feedback: {original_title}"
    description = (
        f"Fix quest following changes_requested on review {review_quest['id']}.\n\n"
        f"Original quest: {original_title}\n"
        f"Branch: {review_quest['branch']}\n\n"
        f"## Review Feedback\n{review_feedback}\n"
    )
    branch = f"fix/{quest_id[-6:]}-{review_quest['branch'].split('/')[-1] if '/' in review_quest['branch'] else review_quest['branch']}"

    assigned_to = original_implementor["id"] if original_implementor else None

    conn.execute(
        "INSERT INTO quests (id, chain_id, parent_quest_id, title, description, tier, type, status, "
        "project_id, branch, req_skills, assigned_to, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            quest_id, chain_id, review_quest["id"],
            title, description,
            review_quest["tier"], "fix",
            "active" if assigned_to else "backlog",
            review_quest["project_id"],
            branch,
            review_quest["req_skills"],
            assigned_to,
            now,
        ),
    )

    log_activity(conn, "guild-master",
                 f"Created fix quest {quest_id} in chain {chain_id[:8]} (review cycle {review_cycles + 1})",
                 quest_id=quest_id, project_id=review_quest["project_id"])
    print(f"  >> Created fix quest [{quest_id}] in chain {chain_id[:8]}")

    if assigned_to and original_implementor:
        conn.execute(
            "UPDATE heroes SET status = 'on_quest', current_quest_id = ? WHERE id = ?",
            (quest_id, assigned_to),
        )
        brief = f"## Quest: {title}\nID: {quest_id}\nBranch: {branch}\n"
        brief += f"Tier: {review_quest['tier']} | Type: fix\n\n{description}\n"
        hero_inbox = INBOX / f"{original_implementor['name']}.md"
        hero_inbox.write_text(brief)
        log_activity(conn, "guild-master",
                     f"Assigned fix quest {quest_id} to {original_implementor['name']}",
                     quest_id=quest_id)
        print(f"  -> Assigned fix [{quest_id}] to {original_implementor['name']}")

    conn.commit()


def check_merge_ready(conn, chain_id):
    """Check if all quests in a completed chain are done and notify for merge approval."""
    chain = conn.execute(
        "SELECT * FROM quest_chains WHERE id = ?", (chain_id,)
    ).fetchone()
    if not chain or chain["status"] != "done":
        return

    pending = conn.execute(
        "SELECT COUNT(*) as cnt FROM quests WHERE chain_id = ? AND status NOT IN ('done')",
        (chain_id,),
    ).fetchone()
    if pending and pending["cnt"] > 0:
        return

    already_pending = conn.execute(
        "SELECT id FROM activity_log WHERE action LIKE ? AND action LIKE '%merge_pending%'",
        (f"%{chain_id[:8]}%",),
    ).fetchone()
    if already_pending:
        return

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO activity_log (id, timestamp, actor, action, quest_id, project_id, level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()), now, "guild-master",
            f"merge_pending: Chain {chain_id[:8]} ready for dev->main merge",
            None, chain["project_id"], "info",
        ),
    )

    try:
        bot = _load_telegram_bot()
        if bot:
            project_name = "unknown"
            if chain["project_id"]:
                _proj = conn.execute(
                    "SELECT name FROM projects WHERE id = ?", (chain["project_id"],)
                ).fetchone()
                if _proj:
                    project_name = _proj["name"]
            bot.notify_merge_ready(chain_id, chain["goal"], project_name)
    except Exception:
        pass

    conn.commit()


# ---------------------------------------------------------------------------
# File lock conflict detection
# ---------------------------------------------------------------------------

def _extract_likely_files(description):
    """Extract file paths from quest description."""
    patterns = [
        r'`([a-zA-Z0-9_/\-\.]+\.[a-zA-Z]+)`',
        r'(?:^|\s)((?:src|lib|app|agents|dashboard)/[a-zA-Z0-9_/\-\.]+)',
    ]
    files = set()
    for pattern in patterns:
        matches = re.findall(pattern, description)
        files.update(matches)
    return list(files)


def check_file_conflicts(conn, quest):
    """Check if quest's likely files conflict with existing locks."""
    likely_files = _extract_likely_files(quest["description"] or "")
    if not likely_files:
        return []

    conflicts = []
    for f in likely_files:
        lock = conn.execute(
            "SELECT * FROM file_locks WHERE file_path = ?", (f,)
        ).fetchone()
        if lock and lock["quest_id"] != quest["id"]:
            conflicts.append((f, lock["quest_id"], lock["hero_id"]))
    return conflicts


def activate_queued_quests(conn):
    """Check if any queued quests can now proceed."""
    queued = conn.execute(
        "SELECT * FROM quests WHERE status = 'queued' ORDER BY created_at ASC"
    ).fetchall()

    for quest in queued:
        conflicts = check_file_conflicts(conn, quest)
        if not conflicts:
            conn.execute("UPDATE quests SET status = 'backlog' WHERE id = ?", (quest["id"],))
            log_activity(conn, "guild-master", f"Quest {quest['id']} unqueued — file conflicts resolved", quest_id=quest["id"])
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
        conflicts = check_file_conflicts(conn, quest)
        if conflicts:
            log_activity(conn, "guild-master",
                         f"Quest {quest['id']} queued — file conflict with {conflicts[0][1]}",
                         quest_id=quest["id"])
            conn.execute("UPDATE quests SET status = 'queued' WHERE id = ?", (quest["id"],))
            conn.commit()
            continue

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

            # Send formatted Telegram escalation
            try:
                _tg_bot = _load_telegram_bot()
                if _tg_bot:
                    _problem = f"Blocked {block_count} times. Hero: {quest['hero_name'] or 'unassigned'}. Title: {quest['title']}"
                    _tg_bot.notify_escalation(quest["id"], _problem)
            except Exception:
                pass

    conn.commit()


CYCLE_TIMEOUT = 600  # 10 minutes


def _handle_stuck_cycle():
    """Called when a cycle exceeds the timeout."""
    handle_error(GuildError.CRITICAL, "Guild Master cycle stuck > 10 minutes, forcing restart")
    # Force the process to restart by raising in main thread
    import _thread
    _thread.interrupt_main()


def _cycle_watchdog(timeout=CYCLE_TIMEOUT):
    """Kill the current cycle if it takes too long."""
    timer = threading.Timer(timeout, _handle_stuck_cycle)
    timer.daemon = True
    timer.start()
    return timer


# ---------------------------------------------------------------------------
# Proactive checks
# ---------------------------------------------------------------------------

def check_idle_prs(conn):
    """Check for review quests that have been active > 24 hours."""
    threshold = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    idle_reviews = conn.execute(
        "SELECT q.*, h.name as hero_name FROM quests q "
        "LEFT JOIN heroes h ON q.assigned_to = h.id "
        "WHERE q.type = 'review' AND q.status = 'active' AND q.created_at < ?",
        (threshold,)
    ).fetchall()

    for quest in idle_reviews:
        already_pinged = conn.execute(
            "SELECT id FROM activity_log WHERE quest_id = ? AND action LIKE '%idle_ping%' AND timestamp > ?",
            (quest["id"], (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat())
        ).fetchone()
        if already_pinged:
            continue

        log_activity(conn, "guild-master", f"idle_ping: Review {quest['id']} idle > 24h, assigned to {quest['hero_name'] or 'unassigned'}", quest_id=quest["id"])

        bot = _load_telegram_bot()
        if bot:
            bot.notify_escalation(quest["id"], f"Review quest idle > 24 hours. Hero: {quest['hero_name'] or 'unassigned'}")

    conn.commit()


def check_project_health(conn):
    """Periodic project health checks - run weekly."""
    last_check = conn.execute(
        "SELECT timestamp FROM activity_log WHERE action LIKE '%weekly_health_check%' ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()

    if last_check:
        last_dt = datetime.fromisoformat(last_check["timestamp"].replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - last_dt).days < 7:
            return

    projects = conn.execute("SELECT * FROM projects WHERE status = 'active'").fetchall()
    for project in projects:
        path = project["path"]
        if not path or not os.path.isdir(path):
            continue

        issues = []

        todo_count = _count_todos(path)
        if todo_count > 20:
            issues.append(f"{todo_count} TODO/FIXME comments found")

        large_files = _find_large_files(path, threshold_kb=500)
        if large_files:
            issues.append(f"{len(large_files)} files > 500KB")

        if issues:
            _create_chore_quest(conn, project, issues)

    log_activity(conn, "guild-master", "weekly_health_check completed")
    conn.commit()


def _count_todos(path):
    count = 0
    skip_dirs = {'.git', 'node_modules', 'target', '__pycache__', 'dist', 'build', '.next', 'vendor'}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if f.endswith(('.py', '.rs', '.ts', '.tsx', '.js', '.jsx', '.go', '.java')):
                try:
                    content = open(os.path.join(root, f), 'r', errors='ignore').read()
                    count += content.count('TODO') + content.count('FIXME') + content.count('HACK')
                except Exception:
                    pass
    return count


def _find_large_files(path, threshold_kb=500):
    large = []
    skip_dirs = {'.git', 'node_modules', 'target', '__pycache__', 'dist', 'build'}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            fp = os.path.join(root, f)
            try:
                if os.path.getsize(fp) > threshold_kb * 1024:
                    large.append(fp)
            except Exception:
                pass
    return large


def _create_chore_quest(conn, project, issues):
    quest_id = f"GLD-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    description = "Auto-generated chore quest from weekly health check:\n\n"
    for issue in issues:
        description += f"- {issue}\n"

    conn.execute(
        "INSERT INTO quests (id, title, description, tier, type, status, project_id, req_skills, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (quest_id, f"[chore] Code health: {project['name']}", description, "COMMON", "chore", "backlog", project["id"], project.get("language", "") or "", now)
    )
    log_activity(conn, "guild-master", f"Auto-created chore quest {quest_id} for {project['name']}", quest_id=quest_id, project_id=project["id"])


def monitor_development_branch(conn):
    """Check if development branch has completed chains ready for main merge."""
    chains = conn.execute(
        "SELECT qc.*, p.path, p.main_branch, p.dev_branch, p.name as project_name "
        "FROM quest_chains qc "
        "JOIN projects p ON qc.project_id = p.id "
        "WHERE qc.status = 'done'"
    ).fetchall()

    for chain in chains:
        if not chain["path"] or not os.path.isdir(chain["path"]):
            continue

        pending = conn.execute(
            "SELECT id FROM activity_log WHERE action LIKE ? AND action LIKE '%merge_pending%'",
            (f"%{chain['id'][:8]}%",),
        ).fetchone()
        if pending:
            continue

        try:
            result = subprocess.run(
                ["git", "-C", chain["path"], "log",
                 f"{chain['main_branch']}..{chain['dev_branch']}", "--oneline"],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout.strip():
                check_merge_ready(conn, chain["id"])
        except Exception:
            pass


def run_cycle(client):
    """Run one Guild Master cycle."""
    bot = _load_telegram_bot()
    if bot:
        bot.flush_queue()

    conn = get_db()

    activate_queued_quests(conn)

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
        "AND chain_id IS NOT NULL AND type IN ('feature', 'bugfix', 'test', 'review', 'refactor', 'fix')"
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

    # Proactive checks
    check_idle_prs(conn)
    check_project_health(conn)

    monitor_development_branch(conn)

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
    crash_times = []

    try:
        while True:
            timer = _cycle_watchdog(CYCLE_TIMEOUT)
            try:
                run_cycle(client)
                timer.cancel()
                crash_times.clear()
            except sqlite3.DatabaseError as e:
                timer.cancel()
                error_msg = str(e)
                if "malformed" in error_msg or "corrupt" in error_msg or "disk" in error_msg:
                    _handle_db_corruption(error_msg)
                else:
                    handle_error(GuildError.WARNING, f"Database error in cycle: {e}")
            except SystemExit:
                timer.cancel()
                raise
            except KeyboardInterrupt:
                timer.cancel()
                # Check if this was from watchdog
                handle_error(GuildError.WARNING, "Cycle interrupted (possible stuck detection)")
                continue
            except Exception as e:
                timer.cancel()
                now = time.time()
                crash_times.append(now)
                crash_times = [t for t in crash_times if now - t <= CRASH_WINDOW_SECONDS]

                if len(crash_times) >= MAX_CONSECUTIVE_CRASHES:
                    handle_error(
                        GuildError.FATAL,
                        f"Guild Master crashed {len(crash_times)} times within {CRASH_WINDOW_SECONDS}s. Last error: {e}",
                    )

                handle_error(GuildError.WARNING, f"Cycle error: {e}")
                print(f"  ! Recovering in 30s...")
                time.sleep(30)
                continue

            # Hourly auto-backup
            if time.time() - last_backup > 3600:
                try:
                    db_backup()
                except Exception as e:
                    handle_error(GuildError.WARNING, f"Backup error: {e}")
                last_backup = time.time()

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n⚔ Guild Master offline")
        log_activity(get_db(), "guild-master", "Guild Master stopped")


if __name__ == "__main__":
    main()
