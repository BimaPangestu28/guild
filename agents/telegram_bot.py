#!/usr/bin/env python3
"""
Telegram Bot — notification and command interface for the Guild system.

Uses only stdlib (urllib.request) — no external dependencies required.
Can run standalone or be imported by guild_master.py.
"""

import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TELEGRAM_API = "https://api.telegram.org/bot{token}"

GUILD_DIR = Path.home() / ".guild"
DB_PATH = GUILD_DIR / "guild.db"
CONFIG_PATH = GUILD_DIR / "config.json"
INBOX = GUILD_DIR / "workspace" / "inbox"
OUTBOX = GUILD_DIR / "workspace" / "outbox"

POLL_INTERVAL = 10  # seconds

# Notification levels
LEVEL_SILENT = 1     # Log only
LEVEL_DASHBOARD = 2  # Log + store for dashboard
LEVEL_TELEGRAM = 3   # Send Telegram message
LEVEL_URGENT = 4     # Send Telegram with warning prefix


# ---------------------------------------------------------------------------
# Telegram Bot Class
# ---------------------------------------------------------------------------

class TelegramBot:
    """Telegram Bot API client using urllib (stdlib only)."""

    def __init__(self, token=None, chat_id=None, notification_level=3):
        """
        Initialize the bot. If token/chat_id are not provided,
        load from ~/.guild/config.json.
        """
        if token and chat_id:
            self.token = token
            self.chat_id = str(chat_id)
            self.notification_level = notification_level
        else:
            config = self._load_config()
            tg = config.get("telegram", {})
            self.token = tg.get("bot_token", "")
            self.chat_id = str(tg.get("chat_id", ""))
            self.notification_level = int(tg.get("notification_level", 3))

        self.api_base = TELEGRAM_API.format(token=self.token)

    @staticmethod
    def _load_config():
        """Load config from ~/.guild/config.json."""
        if not CONFIG_PATH.exists():
            return {}
        try:
            return json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _api_call(self, method, data=None):
        """Make a POST request to the Telegram Bot API."""
        url = f"{self.api_base}/{method}"
        payload = json.dumps(data or {}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"  ! Telegram API error {e.code}: {body}")
            return None
        except urllib.error.URLError as e:
            print(f"  ! Telegram connection error: {e.reason}")
            return None

    def send_message(self, text, parse_mode="Markdown"):
        """Send a text message to the configured chat."""
        return self._api_call("sendMessage", {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        })

    def get_updates(self, offset=0):
        """Long-poll for new messages."""
        result = self._api_call("getUpdates", {
            "offset": offset,
            "timeout": 5,
        })
        if result and result.get("ok"):
            return result.get("result", [])
        return []

    def send_notification(self, level, message):
        """
        Send a notification based on level thresholds.

        Only sends a Telegram message if level >= configured notification_level.
        Level 4 (Urgent) adds a warning prefix.
        """
        # Always log
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        level_names = {1: "SILENT", 2: "DASHBOARD", 3: "TELEGRAM", 4: "URGENT"}
        level_name = level_names.get(level, "UNKNOWN")
        print(f"  [{timestamp}] [{level_name}] {message}")

        # Store for dashboard at level >= 2
        if level >= LEVEL_DASHBOARD:
            self._store_dashboard_notification(level, message)

        # Send Telegram at level >= configured threshold
        if level >= self.notification_level:
            prefix = "\u26a0\ufe0f " if level >= LEVEL_URGENT else ""
            self.send_message(f"{prefix}{message}")

    def notify_quest_complete(self, quest_id, quest_title, hero_name, chain_id=None):
        """Send a formatted quest completion notification."""
        msg = "\u2705 *Quest Complete*\n\n"
        msg += f"Quest: `{quest_id}` \u2014 {quest_title}\n"
        msg += f"Hero: {hero_name}\n"
        if chain_id:
            msg += f"Chain: `{chain_id[:8]}`\n"
        self.send_message(msg)

    def notify_level_up(self, hero_name, hero_class, new_level):
        """Send a formatted hero level-up notification."""
        msg = "\u2b06\ufe0f *Level Up!*\n\n"
        msg += f"{hero_name} ({hero_class}) reached *Level {new_level}*!"
        self.send_message(msg)

    def notify_cost_warning(self, current_cost, cap, percentage):
        """Send a formatted cost warning notification."""
        emoji = "\U0001f534" if percentage > 90 else "\U0001f7e1"
        msg = f"{emoji} *Cost Warning*\n\n"
        msg += f"Today: ${current_cost:.2f} / ${cap:.2f} ({percentage:.0f}%)\n"
        if percentage >= 100:
            msg += "\u26a0\ufe0f All heroes paused \u2014 daily cap reached."
        self.send_message(msg)

    def notify_escalation(self, quest_id, problem, options=None):
        """Send a formatted escalation notification with optional A/B choices."""
        msg = "\U0001f6a8 *Escalation Required*\n\n"
        msg += f"Quest: `{quest_id}`\n"
        msg += f"Problem: {problem}\n"
        if options:
            msg += f"\nOptions:\n"
            for i, opt in enumerate(options):
                msg += f"  {chr(65+i)}) {opt}\n"
            msg += f"\nReply with your choice."
        self.send_message(msg)

    def notify_merge_ready(self, chain_id, goal, project_name):
        """Send a formatted merge-ready notification."""
        msg = "\U0001f500 *Merge Ready*\n\n"
        msg += f"Chain: `{chain_id[:8]}`\n"
        msg += f"Project: {project_name}\n"
        msg += f"Goal: _{goal}_\n\n"
        msg += f"Use `/approve {chain_id[:8]}` or `/reject {chain_id[:8]}`"
        self.send_message(msg)

    @staticmethod
    def _store_dashboard_notification(level, message):
        """Store notification for the dashboard to pick up."""
        notif_dir = GUILD_DIR / "workspace" / "notifications"
        notif_dir.mkdir(parents=True, exist_ok=True)
        notif_file = notif_dir / "recent.jsonl"
        entry = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
        })
        with open(notif_file, "a") as f:
            f.write(entry + "\n")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    """Open the Guild database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Daily Briefing
# ---------------------------------------------------------------------------

def generate_daily_briefing(conn):
    """Generate daily briefing content (max 200 words)."""
    # Active quests
    active = conn.execute(
        "SELECT COUNT(*) FROM quests WHERE status = 'active'"
    ).fetchone()[0]
    backlog = conn.execute(
        "SELECT COUNT(*) FROM quests WHERE status = 'backlog'"
    ).fetchone()[0]
    blocked = conn.execute(
        "SELECT COUNT(*) FROM quests WHERE status = 'blocked'"
    ).fetchone()[0]
    done_today = conn.execute(
        "SELECT COUNT(*) FROM quests WHERE status = 'done' AND completed_at >= date('now')"
    ).fetchone()[0]

    # Heroes
    heroes = conn.execute(
        "SELECT name, status FROM heroes ORDER BY name"
    ).fetchall()

    # Cost today
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cost_row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_log WHERE timestamp LIKE ?",
        (f"{today_str}%",),
    ).fetchone()
    daily_cost = cost_row[0] if cost_row else 0.0

    # Build briefing
    status_emoji = {
        "idle": "\U0001f7e2", "on_quest": "\U0001f535",
        "offline": "\u26ab", "blocked": "\U0001f534",
        "paused": "\U0001f7e0",
    }

    lines = ["\U0001f4dc *Daily Guild Briefing*", ""]

    lines.append("\U0001f5e1 *Quests*")
    lines.append(f"  \U0001f535 Active: {active} | \u26aa Backlog: {backlog}")
    lines.append(f"  \U0001f534 Blocked: {blocked} | \u2705 Done today: {done_today}")
    lines.append("")

    lines.append("\U0001f9d9 *Heroes*")
    for h in heroes:
        emoji = status_emoji.get(h["status"], "\u26aa")
        lines.append(f"  {emoji} {h['name']}: {h['status']}")
    if not heroes:
        lines.append("  No heroes recruited.")
    lines.append("")

    if blocked > 0:
        blocked_quests = conn.execute(
            "SELECT id, title FROM quests WHERE status = 'blocked' LIMIT 3"
        ).fetchall()
        lines.append("\U0001f6a8 *Blocked*")
        for q in blocked_quests:
            lines.append(f"  `{q['id']}` {q['title']}")
        lines.append("")

    lines.append(f"\U0001f4b0 *Cost today:* ${daily_cost:.2f}")

    return "\n".join(lines)


def check_daily_briefing(bot, conn, config):
    """Check if it's time to send daily briefing.

    Reads briefing_time from config (default '09:00'), sends once per day,
    and records state to avoid duplicate sends.
    """
    briefing_time = config.get("daily_briefing_time", "09:00")
    now = datetime.now()
    target_hour, target_min = map(int, briefing_time.split(":"))

    if now.hour == target_hour and now.minute == target_min:
        # Check if already sent today
        today_key = f"briefing_{now.strftime('%Y%m%d')}"
        state_file = GUILD_DIR / "workspace" / ".briefing_state"
        if state_file.exists() and state_file.read_text().strip() == today_key:
            return

        briefing = generate_daily_briefing(conn)
        bot.send_message(briefing, parse_mode="Markdown")
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(today_key)


# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------

def cmd_status(bot):
    """Handle /status — hero roster + active quests summary."""
    conn = get_db()
    heroes = conn.execute(
        "SELECT name, class, status, level FROM heroes ORDER BY name"
    ).fetchall()
    quests = conn.execute(
        "SELECT q.id, q.title, q.tier, q.status, h.name as hero "
        "FROM quests q LEFT JOIN heroes h ON q.assigned_to = h.id "
        "WHERE q.status IN ('active', 'backlog', 'blocked') "
        "ORDER BY q.created_at DESC LIMIT 10"
    ).fetchall()
    conn.close()

    lines = ["*Guild Status*\n"]

    lines.append("*Heroes:*")
    if heroes:
        for h in heroes:
            emoji = {"idle": "🟢", "on_quest": "🔵", "offline": "⚫", "blocked": "🔴"}.get(h["status"], "⚪")
            lines.append(f"  {emoji} {h['name']} ({h['class']}) — Lv.{h['level']} [{h['status']}]")
    else:
        lines.append("  No heroes recruited.")

    lines.append("\n*Active Quests:*")
    if quests:
        for q in quests:
            hero = q["hero"] or "unassigned"
            lines.append(f"  [{q['id'][:10]}] {q['title']} ({q['tier']}, {q['status']}) -> {hero}")
    else:
        lines.append("  No active quests.")

    bot.send_message("\n".join(lines))


def cmd_heroes(bot):
    """Handle /heroes — hero list with status and level."""
    conn = get_db()
    heroes = conn.execute(
        "SELECT name, class, status, level, xp FROM heroes ORDER BY level DESC, name"
    ).fetchall()
    conn.close()

    lines = ["*Hero Roster*\n"]
    if heroes:
        for h in heroes:
            emoji = {"idle": "🟢", "on_quest": "🔵", "offline": "⚫", "blocked": "🔴"}.get(h["status"], "⚪")
            lines.append(f"{emoji} *{h['name']}* — {h['class']}")
            lines.append(f"    Level {h['level']} | XP: {h['xp']} | Status: {h['status']}")
    else:
        lines.append("No heroes recruited yet.")

    bot.send_message("\n".join(lines))


def cmd_quests(bot):
    """Handle /quests — quest board summary."""
    conn = get_db()
    quests = conn.execute(
        "SELECT q.id, q.title, q.tier, q.type, q.status, q.branch, h.name as hero "
        "FROM quests q LEFT JOIN heroes h ON q.assigned_to = h.id "
        "WHERE q.status IN ('active', 'backlog', 'blocked') "
        "ORDER BY CASE q.status "
        "  WHEN 'active' THEN 1 WHEN 'blocked' THEN 2 WHEN 'backlog' THEN 3 END, "
        "q.created_at DESC LIMIT 15"
    ).fetchall()
    conn.close()

    lines = ["*Quest Board*\n"]
    if quests:
        for q in quests:
            hero = q["hero"] or "unassigned"
            status_icon = {"active": "🔵", "blocked": "🔴", "backlog": "⚪"}.get(q["status"], "⚪")
            lines.append(f"{status_icon} `{q['id'][:10]}` {q['title']}")
            lines.append(f"    {q['tier']} | {q['type']} | {q['status']} | {hero}")
    else:
        lines.append("No quests on the board.")

    bot.send_message("\n".join(lines))


def cmd_report(bot):
    """Handle /report — read guild-master.md outbox."""
    gm_outbox = OUTBOX / "guild-master.md"
    if gm_outbox.exists():
        content = gm_outbox.read_text().strip()
        if content:
            # Truncate if too long for Telegram (4096 char limit)
            if len(content) > 3900:
                content = content[:3900] + "\n\n_(truncated)_"
            bot.send_message(content)
        else:
            bot.send_message("No recent Guild Master report.")
    else:
        bot.send_message("No Guild Master report found.")


def cmd_pause(bot):
    """Handle /pause — set all heroes to offline."""
    conn = get_db()
    count = conn.execute(
        "UPDATE heroes SET status = 'offline' WHERE status IN ('idle', 'on_quest')"
    ).rowcount
    conn.commit()
    conn.close()
    bot.send_message(f"Paused {count} hero(es). All set to offline.")


def cmd_resume(bot):
    """Handle /resume — set all heroes to idle."""
    conn = get_db()
    count = conn.execute(
        "UPDATE heroes SET status = 'idle' WHERE status = 'offline'"
    ).rowcount
    conn.commit()
    conn.close()
    bot.send_message(f"Resumed {count} hero(es). All set to idle.")


def cmd_goal(bot, text):
    """Handle /goal {text} — write to guild-master inbox."""
    if not text.strip():
        bot.send_message("Usage: `/goal <description>`")
        return

    INBOX.mkdir(parents=True, exist_ok=True)
    inbox_file = INBOX / "guild-master.md"

    # Append to inbox (don't overwrite existing goals)
    existing = inbox_file.read_text().strip() if inbox_file.exists() else ""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    new_content = f"## Goal — {timestamp}\n{text.strip()}\n"

    if existing:
        inbox_file.write_text(f"{existing}\n\n{new_content}")
    else:
        inbox_file.write_text(new_content)

    bot.send_message(f"Goal submitted to Guild Master:\n_{text.strip()}_")


def cmd_approve(bot, text):
    """Handle /approve {chain_id} — approve chain and create dev->main PR."""
    import uuid as _uuid
    chain_id = text.strip()
    if not chain_id:
        bot.send_message("Usage: `/approve <chain_id>`")
        return

    conn = get_db()

    row = conn.execute(
        "SELECT qc.id, qc.goal, qc.status, qc.project_id FROM quest_chains qc WHERE qc.id LIKE ?",
        (f"{chain_id}%",),
    ).fetchone()

    if not row:
        conn.close()
        bot.send_message(f"Chain `{chain_id}` not found.")
        return

    if row["status"] not in ("done", "approved"):
        conn.close()
        bot.send_message(f"Chain `{row['id'][:8]}` is not ready for merge (status: {row['status']}).")
        return

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE quest_chains SET status = 'approved', completed_at = ? WHERE id = ?",
        (now, row["id"]),
    )

    conn.execute(
        "INSERT INTO activity_log (id, timestamp, actor, action, quest_id, project_id, level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(_uuid.uuid4()), now, "telegram-bot",
         f"Chain {row['id'][:8]} approved for merge via Telegram",
         None, row["project_id"], "info"),
    )
    conn.commit()

    pr_url = None
    if row["project_id"]:
        project = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (row["project_id"],)
        ).fetchone()
        if project:
            try:
                from git_workflow import create_merge_pr
                pr_url = create_merge_pr(
                    project["path"],
                    "development",
                    "main",
                    f"Merge: {row['goal']}",
                    f"Chain `{row['id'][:8]}` approved for merge.\n\nGoal: {row['goal']}",
                )
            except Exception as e:
                bot.send_message(f"Chain approved but PR creation failed: {e}")

    conn.execute(
        "INSERT INTO activity_log (id, timestamp, actor, action, quest_id, project_id, level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(_uuid.uuid4()), now, "telegram-bot",
         f"merge_approved: Chain {row['id'][:8]} PR: {pr_url or 'manual'}",
         None, row["project_id"], "info"),
    )
    conn.commit()
    conn.close()

    if pr_url:
        bot.send_message(f"Chain `{row['id'][:8]}` approved.\nPR created: {pr_url}\nGoal: _{row['goal']}_")
    else:
        bot.send_message(f"Chain `{row['id'][:8]}` approved for merge.\nGoal: _{row['goal']}_")


def cmd_reject(bot, text):
    """Handle /reject {chain_id} — reject merge, keep chain on development."""
    import uuid as _uuid
    parts = text.strip().split(None, 1)
    chain_id = parts[0] if parts else ""
    reason = parts[1] if len(parts) > 1 else "No reason provided"

    if not chain_id:
        bot.send_message("Usage: `/reject <chain_id> [reason]`")
        return

    conn = get_db()

    row = conn.execute(
        "SELECT id, goal, status, project_id FROM quest_chains WHERE id LIKE ?",
        (f"{chain_id}%",),
    ).fetchone()

    if not row:
        conn.close()
        bot.send_message(f"Chain `{chain_id}` not found.")
        return

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO activity_log (id, timestamp, actor, action, quest_id, project_id, level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(_uuid.uuid4()), now, "telegram-bot",
         f"merge_rejected: Chain {row['id'][:8]} — {reason}",
         None, row["project_id"], "info"),
    )
    conn.commit()
    conn.close()

    bot.send_message(
        f"Chain `{row['id'][:8]}` merge rejected.\n"
        f"Reason: _{reason}_\n"
        f"Chain remains on development."
    )


def cmd_cost(bot):
    """Handle /cost — query activity_log for api_cost entries today."""
    conn = get_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    rows = conn.execute(
        "SELECT actor, action FROM activity_log "
        "WHERE action LIKE 'api_cost:%' AND timestamp LIKE ?",
        (f"{today}%",),
    ).fetchall()
    conn.close()

    total_tokens = 0
    actor_tokens = {}
    for row in rows:
        match = re.search(r"api_cost:\s*(\d+)\s*tokens", row["action"])
        if match:
            tokens = int(match.group(1))
            total_tokens += tokens
            actor = row["actor"]
            actor_tokens[actor] = actor_tokens.get(actor, 0) + tokens

    lines = [f"*Cost Report — {today}*\n"]
    if actor_tokens:
        for actor, tokens in sorted(actor_tokens.items()):
            # Rough cost estimate: ~$3 per 1M tokens (blended)
            cost_est = tokens * 3.0 / 1_000_000
            lines.append(f"  {actor}: {tokens:,} tokens (~${cost_est:.4f})")
        lines.append(f"\n*Total:* {total_tokens:,} tokens")
    else:
        lines.append("No API cost entries today.")

    bot.send_message("\n".join(lines))


def cmd_help(bot):
    """Handle /help — list available commands."""
    help_text = (
        "*Guild Telegram Bot Commands*\n\n"
        "/status — Guild overview (heroes + quests)\n"
        "/heroes — Hero roster with levels\n"
        "/quests — Quest board summary\n"
        "/report — Latest Guild Master report\n"
        "/pause — Set all heroes to offline\n"
        "/resume — Set all heroes to idle\n"
        "/goal `<text>` — Submit goal to Guild Master\n"
        "/approve `<chain_id>` — Approve chain and create dev->main PR\n"
        "/reject `<chain_id> [reason]` — Reject merge, keep on dev\n"
        "/cost — Today's API cost breakdown\n"
        "/help — Show this help message"
    )
    bot.send_message(help_text)


# ---------------------------------------------------------------------------
# Command Router
# ---------------------------------------------------------------------------

COMMANDS = {
    "/status": lambda bot, _: cmd_status(bot),
    "/heroes": lambda bot, _: cmd_heroes(bot),
    "/quests": lambda bot, _: cmd_quests(bot),
    "/report": lambda bot, _: cmd_report(bot),
    "/pause": lambda bot, _: cmd_pause(bot),
    "/resume": lambda bot, _: cmd_resume(bot),
    "/goal": lambda bot, args: cmd_goal(bot, args),
    "/approve": lambda bot, args: cmd_approve(bot, args),
    "/reject": lambda bot, args: cmd_reject(bot, args),
    "/cost": lambda bot, _: cmd_cost(bot),
    "/help": lambda bot, _: cmd_help(bot),
}


def handle_message(bot, message):
    """Parse and route a Telegram message to the appropriate handler."""
    text = message.get("text", "").strip()
    if not text.startswith("/"):
        return

    # Split command and arguments
    parts = text.split(None, 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    # Strip @botname suffix if present (e.g., /status@MyGuildBot)
    if "@" in command:
        command = command.split("@")[0]

    handler = COMMANDS.get(command)
    if handler:
        try:
            handler(bot, args)
        except Exception as e:
            bot.send_message(f"Error handling `{command}`: {e}")
            print(f"  ! Error handling {command}: {e}")
    else:
        bot.send_message(f"Unknown command: `{command}`\nUse /help for available commands.")


# ---------------------------------------------------------------------------
# Main polling loop
# ---------------------------------------------------------------------------

def main():
    """Standalone polling loop for the Telegram bot."""
    if not CONFIG_PATH.exists():
        print("Error: Config not found. Run 'guild setup-telegram' first.")
        sys.exit(1)

    if not DB_PATH.exists():
        print("Error: Guild not initialized. Run 'guild init' first.")
        sys.exit(1)

    bot = TelegramBot()

    if not bot.token or not bot.chat_id:
        print("Error: Telegram bot_token or chat_id not configured.")
        print("  Run 'guild setup-telegram' to set up.")
        sys.exit(1)

    print("Guild Telegram Bot online")
    print(f"  Chat ID: {bot.chat_id}")
    print(f"  Notification level: {bot.notification_level}")
    print(f"  Polling every {POLL_INTERVAL}s")
    print(f"  Press Ctrl+C to stop\n")

    bot.send_notification(LEVEL_TELEGRAM, "Guild Telegram Bot started.")

    # Load config for daily briefing settings
    config = bot._load_config()

    offset = 0

    try:
        while True:
            try:
                updates = bot.get_updates(offset=offset)
                for update in updates:
                    offset = update["update_id"] + 1
                    msg = update.get("message")
                    if msg:
                        # Only respond to messages from the configured chat
                        msg_chat_id = str(msg.get("chat", {}).get("id", ""))
                        if msg_chat_id == bot.chat_id:
                            handle_message(bot, msg)
                        else:
                            print(f"  ! Ignored message from chat {msg_chat_id}")
            except Exception as e:
                print(f"  ! Poll error: {e}")

            # Check if daily briefing should be sent
            try:
                conn = get_db()
                check_daily_briefing(bot, conn, config)
                conn.close()
            except Exception as e:
                print(f"  ! Briefing check error: {e}")

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nGuild Telegram Bot offline")
        bot.send_notification(LEVEL_TELEGRAM, "Guild Telegram Bot stopped.")


if __name__ == "__main__":
    main()
