#!/usr/bin/env python3
"""
Hero Runtime — spawns and manages Claude Code CLI sessions for hero agents.

Uses the Claude Code CLI (`claude`) as a subprocess, managing lifecycle,
crash recovery, rate-limit detection, and circuit-breaker logic.
"""

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


GUILD_DIR = Path.home() / ".guild"
DB_PATH = GUILD_DIR / "guild.db"
MEMORY_DIR = GUILD_DIR / "workspace" / "memory"
INBOX = GUILD_DIR / "workspace" / "inbox"
OUTBOX = GUILD_DIR / "workspace" / "outbox"

HEARTBEAT_INTERVAL = 60  # seconds
RATE_LIMIT_TIMEOUT = 300  # 5 minutes with no output
MAX_RESTARTS = 3
DEADMAN_TIMER = 7200  # 2 hours with no commits -> escalate
ERROR_WINDOW = 10  # track last N stderr lines
ERROR_REPEAT_THRESHOLD = 3  # same error repeated this many times -> circuit break
MAX_TURNS = 50
MAX_TOKENS_PER_QUEST = 500_000


def get_db():
    """Get a database connection using the same pattern as guild_master.py."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def log_activity(conn, actor, action, quest_id=None, project_id=None, level="info"):
    """Log an activity entry to the database."""
    conn.execute(
        "INSERT INTO activity_log (id, timestamp, actor, action, quest_id, project_id, level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            datetime.now(timezone.utc).isoformat(),
            actor,
            action,
            quest_id,
            project_id,
            level,
        ),
    )
    conn.commit()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class HeroSession:
    """Manages a single Claude Code CLI session for one hero."""

    def __init__(self, hero_id, hero_name, quest_id, project_path, claude_md_path,
                 mcp_config_path=None):
        self.hero_id = hero_id
        self.hero_name = hero_name
        self.quest_id = quest_id
        self.project_path = project_path
        self.claude_md_path = claude_md_path
        self.mcp_config_path = mcp_config_path

        self.process = None
        self.pid = None
        self.started_at = None
        self.last_output_at = None
        self.status = "init"  # init, running, rate_limited, stopped, crashed

        # Circuit breaker state
        self.stderr_buffer = deque(maxlen=ERROR_WINDOW)
        self.restart_count = 0

    def start(self):
        """Spawn the claude CLI process and record PID in DB.

        Returns the PID of the spawned process.
        """
        cmd = [
            "claude",
            "--print",
            "--output-format", "stream-json",
            "--claude-md", str(self.claude_md_path),
            "--max-turns", str(MAX_TURNS),
        ]

        # Read the quest brief from the hero's inbox as the prompt
        inbox_file = INBOX / f"{self.hero_name}.md"
        prompt = ""
        if inbox_file.exists():
            prompt = inbox_file.read_text().strip()

        if prompt:
            cmd.extend(["--prompt", prompt])

        self.process = subprocess.Popen(
            cmd,
            cwd=str(self.project_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )

        self.pid = self.process.pid
        self.started_at = time.time()
        self.last_output_at = time.time()
        self.status = "running"

        # Update DB
        conn = get_db()
        try:
            conn.execute(
                "UPDATE heroes SET session_pid = ?, status = 'on_quest', last_active = ? WHERE id = ?",
                (self.pid, _now_iso(), self.hero_id),
            )
            conn.commit()
            log_activity(
                conn,
                self.hero_name,
                f"Session started (PID {self.pid}) for quest {self.quest_id}",
                quest_id=self.quest_id,
            )
        finally:
            conn.close()

        return self.pid

    def stop(self):
        """Send SIGTERM to the process, set hero idle, clear PID in DB."""
        if self.process and self.is_alive():
            try:
                os.kill(self.pid, signal.SIGTERM)
                # Give it a moment to terminate gracefully
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.kill(self.pid, signal.SIGKILL)
                    self.process.wait(timeout=5)
            except ProcessLookupError:
                pass  # Already dead

        self.status = "stopped"

        conn = get_db()
        try:
            conn.execute(
                "UPDATE heroes SET session_pid = NULL, status = 'idle', last_active = ? WHERE id = ?",
                (_now_iso(), self.hero_id),
            )
            conn.commit()
            log_activity(
                conn,
                self.hero_name,
                f"Session stopped (was PID {self.pid})",
                quest_id=self.quest_id,
            )
        finally:
            conn.close()

    def is_alive(self):
        """Check if the PID is still running."""
        if not self.pid:
            return False
        try:
            os.kill(self.pid, 0)  # Signal 0: check existence without killing
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we lack permission (shouldn't happen for our children)
            return True

    def get_output(self):
        """Read any buffered stdout/stderr (non-blocking).

        Returns a dict with 'stdout' and 'stderr' contents.
        """
        stdout_data = b""
        stderr_data = b""

        if not self.process:
            return {"stdout": "", "stderr": ""}

        # Non-blocking read from stdout
        if self.process.stdout and self.process.stdout.readable():
            try:
                import select as sel
                readable, _, _ = sel.select([self.process.stdout], [], [], 0)
                if readable:
                    chunk = self.process.stdout.read1(65536)
                    if chunk:
                        stdout_data = chunk
                        self.last_output_at = time.time()
            except (OSError, ValueError):
                pass

        # Non-blocking read from stderr
        if self.process.stderr and self.process.stderr.readable():
            try:
                import select as sel
                readable, _, _ = sel.select([self.process.stderr], [], [], 0)
                if readable:
                    chunk = self.process.stderr.read1(65536)
                    if chunk:
                        stderr_data = chunk
            except (OSError, ValueError):
                pass

        stdout_str = stdout_data.decode("utf-8", errors="replace")
        stderr_str = stderr_data.decode("utf-8", errors="replace")

        # Track stderr lines for circuit breaker
        if stderr_str:
            for line in stderr_str.strip().splitlines():
                line = line.strip()
                if line:
                    self.stderr_buffer.append(line)

        # Update last_active in DB if we got output
        if stdout_str:
            conn = get_db()
            try:
                conn.execute(
                    "UPDATE heroes SET last_active = ? WHERE id = ?",
                    (_now_iso(), self.hero_id),
                )
                conn.commit()
            finally:
                conn.close()

        return {"stdout": stdout_str, "stderr": stderr_str}

    def check_mcp_health(self):
        """Check if MCPs are still healthy during session."""
        if not self.mcp_config_path:
            return

        try:
            config = json.loads(Path(self.mcp_config_path).read_text())
            for name, server in config.get("mcpServers", {}).items():
                if "url" in server:
                    try:
                        from urllib.request import urlopen, Request
                        req = Request(server["url"], method="HEAD")
                        urlopen(req, timeout=5)
                    except Exception:
                        self._log_mcp_warning(name)
                elif "command" in server:
                    import shutil
                    if not shutil.which(server["command"]):
                        self._log_mcp_warning(name)
        except Exception:
            pass

    def _log_mcp_warning(self, mcp_name):
        """Log MCP unreachable warning."""
        print(f"  WARN: MCP '{mcp_name}' unreachable during session for {self.hero_name}")
        conn = get_db()
        try:
            log_activity(
                conn,
                self.hero_name,
                f"MCP '{mcp_name}' unreachable during session",
                quest_id=self.quest_id,
                level="warning",
            )
        finally:
            conn.close()


class SessionManager:
    """Manages all active hero sessions."""

    def __init__(self):
        self.sessions = {}  # hero_id -> HeroSession
        self._restart_counts = {}  # quest_id -> restart count

    def start_hero(self, hero_id):
        """Look up hero's current quest and project, then start a session.

        Returns the HeroSession or None if the hero cannot be started.
        """
        conn = get_db()
        try:
            hero = conn.execute(
                "SELECT h.id, h.name, h.current_quest_id, h.status "
                "FROM heroes h WHERE h.id = ?",
                (hero_id,),
            ).fetchone()

            if not hero:
                print(f"  ! Hero {hero_id} not found")
                return None

            quest_id = hero["current_quest_id"]
            if not quest_id:
                print(f"  ! Hero {hero['name']} has no assigned quest")
                return None

            quest = conn.execute(
                "SELECT q.id, q.project_id, q.branch, q.title "
                "FROM quests q WHERE q.id = ?",
                (quest_id,),
            ).fetchone()

            if not quest:
                print(f"  ! Quest {quest_id} not found")
                return None

            # Resolve project path
            project = conn.execute(
                "SELECT path, name FROM projects WHERE id = ?",
                (quest["project_id"],),
            ).fetchone()

            if not project:
                print(f"  ! Project for quest {quest_id} not found")
                return None

            project_path = Path(project["path"])
            if not project_path.exists():
                print(f"  ! Project path does not exist: {project_path}")
                return None

            # Assemble CLAUDE.md path
            hero_memory_dir = MEMORY_DIR / "heroes" / hero["name"]
            hero_memory_dir.mkdir(parents=True, exist_ok=True)
            claude_md_path = hero_memory_dir / "CLAUDE.md"

            # If CLAUDE.md doesn't exist yet, create a minimal one
            if not claude_md_path.exists():
                _assemble_claude_md(
                    hero["name"], quest, project["name"], claude_md_path
                )

            session = HeroSession(
                hero_id=hero_id,
                hero_name=hero["name"],
                quest_id=quest_id,
                project_path=project_path,
                claude_md_path=claude_md_path,
            )

            pid = session.start()
            self.sessions[hero_id] = session
            print(f"  + Started session for {hero['name']} (PID {pid}), quest {quest_id}")
            return session

        finally:
            conn.close()

    def stop_hero(self, hero_id):
        """Stop a hero session, create WIP commit, and remove from tracking."""
        session = self.sessions.get(hero_id)
        if session:
            self._wip_commit(session)
            session.stop()
            del self.sessions[hero_id]
            print(f"  - Stopped session for {session.hero_name}")
        else:
            print(f"  ! No active session for hero {hero_id}")

    def _wip_commit(self, session):
        """Create a WIP commit for paused hero if there are uncommitted changes."""
        if not session.quest_id:
            return
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(session.project_path),
                capture_output=True, text=True, timeout=10,
            )
            if result.stdout.strip():
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=str(session.project_path),
                    check=True, timeout=10,
                )
                msg = f"[{session.quest_id}] WIP -- paused by developer -- {session.hero_name}"
                subprocess.run(
                    ["git", "commit", "-m", msg],
                    cwd=str(session.project_path),
                    check=True, timeout=10,
                )
                print(f"  ~ WIP commit created for {session.hero_name}")
        except Exception:
            pass

    def stop_all(self):
        """Stop all active sessions."""
        hero_ids = list(self.sessions.keys())
        for hero_id in hero_ids:
            self.stop_hero(hero_id)
        print(f"  Stopped {len(hero_ids)} session(s)")

    def heartbeat(self):
        """Check all sessions, detect dead PIDs and handle recovery.

        Called periodically (every HEARTBEAT_INTERVAL seconds).
        """
        dead_sessions = []

        for hero_id, session in list(self.sessions.items()):
            # Read any buffered output (keeps last_output_at updated)
            output = session.get_output()

            # Check MCP health periodically
            session.check_mcp_health()

            if not session.is_alive():
                dead_sessions.append((hero_id, session))
                continue

            # Rate limit detection: no output for > 5 minutes
            if session.last_output_at and session.status == "running":
                silence_duration = time.time() - session.last_output_at
                if silence_duration > RATE_LIMIT_TIMEOUT:
                    self._handle_silence(hero_id, session)

            # Circuit breaker: repeated errors in stderr
            if session.stderr_buffer:
                self._check_circuit_breaker(hero_id, session)

            # Max tokens per quest circuit breaker
            if self.check_token_usage(session.hero_name):
                print(f"  !! Hero {session.hero_name} exceeded max tokens per quest -- terminating")
                session.stop()
                del self.sessions[hero_id]
                conn = get_db()
                try:
                    conn.execute(
                        "UPDATE quests SET status = 'blocked' WHERE id = ?",
                        (session.quest_id,),
                    )
                    conn.execute(
                        "UPDATE heroes SET status = 'blocked', session_pid = NULL WHERE id = ?",
                        (hero_id,),
                    )
                    conn.commit()
                    log_activity(
                        conn,
                        session.hero_name,
                        f"Quest {session.quest_id} blocked: exceeded {MAX_TOKENS_PER_QUEST} token limit",
                        quest_id=session.quest_id,
                        level="error",
                    )
                finally:
                    conn.close()
                continue

            # Dead-man timer: session running too long with no commits
            if session.started_at:
                runtime = time.time() - session.started_at
                if runtime > DEADMAN_TIMER:
                    self._check_deadman_timer(hero_id, session)

        # Safety checks for all active sessions
        for hero_id, session in list(self.sessions.items()):
            self.check_scope_violation(hero_id, session)
            self.check_branch_violation(hero_id, session)

        # Handle dead sessions
        for hero_id, session in dead_sessions:
            self._handle_dead_session(hero_id, session)

    def recover_hero(self, hero_id):
        """Re-start a hero session with recovery context injected into CLAUDE.md."""
        conn = get_db()
        try:
            hero = conn.execute(
                "SELECT id, name, current_quest_id FROM heroes WHERE id = ?",
                (hero_id,),
            ).fetchone()

            if not hero or not hero["current_quest_id"]:
                print(f"  ! Cannot recover hero {hero_id}: no active quest")
                return None

            quest = conn.execute(
                "SELECT q.id, q.project_id, q.title "
                "FROM quests q WHERE q.id = ?",
                (hero["current_quest_id"],),
            ).fetchone()

            if not quest:
                return None

            project = conn.execute(
                "SELECT path, name FROM projects WHERE id = ?",
                (quest["project_id"],),
            ).fetchone()

            if not project:
                return None

            # Inject recovery context into CLAUDE.md
            claude_md_path = MEMORY_DIR / "heroes" / hero["name"] / "CLAUDE.md"
            _inject_recovery_context(
                hero["name"], quest, project, claude_md_path
            )

            log_activity(
                conn,
                hero["name"],
                f"Recovering session for quest {quest['id']}",
                quest_id=quest["id"],
                level="warning",
            )
        finally:
            conn.close()

        # Start a new session
        return self.start_hero(hero_id)

    def get_status(self):
        """Return a dict of all session statuses."""
        statuses = {}
        for hero_id, session in self.sessions.items():
            alive = session.is_alive()
            silence = None
            if session.last_output_at:
                silence = round(time.time() - session.last_output_at, 1)

            statuses[hero_id] = {
                "hero_name": session.hero_name,
                "quest_id": session.quest_id,
                "pid": session.pid,
                "status": session.status,
                "alive": alive,
                "started_at": session.started_at,
                "silence_seconds": silence,
                "restart_count": self._restart_counts.get(session.quest_id, 0),
                "stderr_recent": list(session.stderr_buffer)[-3:] if session.stderr_buffer else [],
            }
        return statuses

    def check_token_usage(self, hero_name):
        """Check if hero's current quest has exceeded token limit."""
        try:
            conn = get_db()
            hero = conn.execute(
                "SELECT current_quest_id FROM heroes WHERE name = ?",
                (hero_name,),
            ).fetchone()
            if not hero or not hero["current_quest_id"]:
                conn.close()
                return False

            quest_id = hero["current_quest_id"]
            row = conn.execute(
                "SELECT COALESCE(SUM(input_tokens + output_tokens), 0) as total "
                "FROM cost_log WHERE quest_id = ?",
                (quest_id,),
            ).fetchone()
            conn.close()

            if row and row["total"] > MAX_TOKENS_PER_QUEST:
                return True
        except Exception:
            pass
        return False

    def check_scope_violation(self, hero_id, session):
        """Check if hero modified files outside their assigned project."""
        try:
            conn = get_db()
            hero = conn.execute("SELECT * FROM heroes WHERE id = ?", (hero_id,)).fetchone()
            if not hero or not hero["current_quest_id"]:
                conn.close()
                return

            quest = conn.execute("SELECT * FROM quests WHERE id = ?", (hero["current_quest_id"],)).fetchone()
            if not quest or not quest["project_id"]:
                conn.close()
                return

            project = conn.execute("SELECT * FROM projects WHERE id = ?", (quest["project_id"],)).fetchone()
            if not project or not project["path"]:
                conn.close()
                return

            project_path = os.path.abspath(project["path"])

            result = subprocess.run(
                ["git", "-C", project_path, "diff", "--name-only", "HEAD~1..HEAD"],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                conn.close()
                return

            violations = []
            for file_path in result.stdout.strip().split('\n'):
                if not file_path:
                    continue
                full_path = os.path.abspath(os.path.join(project_path, file_path))
                if not full_path.startswith(project_path):
                    violations.append(file_path)

            if violations:
                log_activity(
                    conn, session.hero_name,
                    f"SCOPE VIOLATION: {session.hero_name} modified files outside project: {', '.join(violations[:5])}",
                    quest_id=quest["id"], project_id=quest["project_id"], level="warning",
                )

                subprocess.run(
                    ["git", "-C", project_path, "revert", "--no-edit", "HEAD"],
                    capture_output=True, timeout=30
                )

                log_activity(
                    conn, session.hero_name,
                    f"Auto-reverted out-of-scope changes by {session.hero_name}",
                    quest_id=quest["id"], project_id=quest["project_id"], level="warning",
                )

            conn.close()
        except Exception:
            pass

    def check_branch_violation(self, hero_id, session):
        """Check if hero is on main/master branch."""
        try:
            conn = get_db()
            hero = conn.execute("SELECT * FROM heroes WHERE id = ?", (hero_id,)).fetchone()
            if not hero or not hero["current_quest_id"]:
                conn.close()
                return

            quest = conn.execute("SELECT * FROM quests WHERE id = ?", (hero["current_quest_id"],)).fetchone()
            if not quest or not quest["project_id"]:
                conn.close()
                return

            project = conn.execute("SELECT * FROM projects WHERE id = ?", (quest["project_id"],)).fetchone()
            if not project or not project["path"]:
                conn.close()
                return

            result = subprocess.run(
                ["git", "-C", project["path"], "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=10
            )

            current_branch = result.stdout.strip()
            protected = {project["main_branch"] if "main_branch" in project.keys() else "main", "master"}

            if current_branch in protected:
                log_activity(
                    conn, session.hero_name,
                    f"BRANCH VIOLATION: {session.hero_name} on protected branch '{current_branch}' — suspending",
                    quest_id=quest["id"], project_id=quest["project_id"], level="warning",
                )

                if quest["branch"]:
                    subprocess.run(
                        ["git", "-C", project["path"], "checkout", quest["branch"]],
                        capture_output=True, timeout=10
                    )

                conn.execute("UPDATE heroes SET status = 'suspended' WHERE id = ?", (hero_id,))
                conn.commit()

                try:
                    from telegram_bot import TelegramBot
                    bot = TelegramBot()
                    if bot.token and bot.chat_id:
                        bot.notify_escalation(
                            quest["id"],
                            f"Hero {session.hero_name} attempted to work on protected branch '{current_branch}'. Hero suspended.",
                        )
                except Exception:
                    pass

            conn.close()
        except Exception:
            pass

    # --- Internal helpers ---

    def _handle_silence(self, hero_id, session):
        """Handle a session that has been silent for too long."""
        # Check stderr for rate limit indicators
        recent_stderr = " ".join(session.stderr_buffer)
        is_rate_limited = any(
            indicator in recent_stderr.lower()
            for indicator in ["rate limit", "429", "too many requests", "retry-after"]
        )

        conn = get_db()
        try:
            if is_rate_limited:
                session.status = "rate_limited"
                conn.execute(
                    "UPDATE heroes SET status = 'resting', last_active = ? WHERE id = ?",
                    (_now_iso(), hero_id),
                )
                conn.commit()
                log_activity(
                    conn,
                    session.hero_name,
                    "Rate limited, entering rest mode",
                    quest_id=session.quest_id,
                )
                print(f"  ~ {session.hero_name}: rate limited, resting")
            else:
                # Not rate limited, treat as potential crash
                print(f"  ! {session.hero_name}: silent for >{RATE_LIMIT_TIMEOUT}s, treating as crash")
                session.stop()
                del self.sessions[hero_id]
                self._attempt_recovery(hero_id, session)
        finally:
            conn.close()

    def _check_circuit_breaker(self, hero_id, session):
        """Check for repeated errors and trip the circuit breaker if needed."""
        if len(session.stderr_buffer) < ERROR_REPEAT_THRESHOLD:
            return

        # Check if the same error appears repeatedly
        recent = list(session.stderr_buffer)
        last_error = recent[-1]
        repeat_count = sum(1 for line in recent if line == last_error)

        if repeat_count >= ERROR_REPEAT_THRESHOLD:
            print(f"  ! {session.hero_name}: circuit breaker tripped — repeated error: {last_error[:80]}")
            session.stop()
            del self.sessions[hero_id]

            conn = get_db()
            try:
                conn.execute(
                    "UPDATE quests SET status = 'blocked' WHERE id = ?",
                    (session.quest_id,),
                )
                conn.execute(
                    "UPDATE heroes SET status = 'blocked', session_pid = NULL WHERE id = ?",
                    (hero_id,),
                )
                conn.commit()
                log_activity(
                    conn,
                    session.hero_name,
                    f"Circuit breaker: quest {session.quest_id} blocked due to repeated errors",
                    quest_id=session.quest_id,
                    level="error",
                )
            finally:
                conn.close()

    def _check_deadman_timer(self, hero_id, session):
        """Check if a long-running session has made any commits."""
        project_path = session.project_path
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-1", "--since=2 hours ago"],
                cwd=str(project_path),
                capture_output=True,
                text=True,
                timeout=10,
            )
            has_recent_commits = bool(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            has_recent_commits = False

        if not has_recent_commits:
            print(f"  ! {session.hero_name}: dead-man timer — no commits in {DEADMAN_TIMER}s, escalating")
            conn = get_db()
            try:
                log_activity(
                    conn,
                    session.hero_name,
                    f"Dead-man timer: quest {session.quest_id} running >{DEADMAN_TIMER}s with no commits",
                    quest_id=session.quest_id,
                    level="error",
                )
            finally:
                conn.close()

    def _handle_dead_session(self, hero_id, session):
        """Handle a session whose process has died."""
        print(f"  ! {session.hero_name}: session died (was PID {session.pid})")
        session.status = "crashed"

        quest_was_active = session.quest_id is not None

        conn = get_db()
        try:
            conn.execute(
                "UPDATE heroes SET status = 'offline', session_pid = NULL, last_active = ? WHERE id = ?",
                (_now_iso(), hero_id),
            )
            conn.commit()
            log_activity(
                conn,
                session.hero_name,
                f"Session crashed (PID {session.pid})",
                quest_id=session.quest_id,
                level="warning",
            )
        finally:
            conn.close()

        if quest_was_active:
            try:
                from telegram_bot import TelegramBot
                bot = TelegramBot()
                if bot.token and bot.chat_id:
                    bot.send_message(
                        f"⚠️ Hero {session.hero_name} crashed during active quest "
                        f"{session.quest_id}. Attempting recovery."
                    )
            except Exception:
                pass

        del self.sessions[hero_id]
        self._attempt_recovery(hero_id, session)

    def _attempt_recovery(self, hero_id, session):
        """Attempt to recover a crashed session, respecting restart limits."""
        quest_id = session.quest_id
        count = self._restart_counts.get(quest_id, 0)

        if count >= MAX_RESTARTS:
            print(f"  ! {session.hero_name}: max restarts ({MAX_RESTARTS}) reached for quest {quest_id}, marking blocked")
            conn = get_db()
            try:
                conn.execute(
                    "UPDATE quests SET status = 'blocked' WHERE id = ?",
                    (quest_id,),
                )
                conn.execute(
                    "UPDATE heroes SET status = 'blocked' WHERE id = ?",
                    (hero_id,),
                )
                conn.commit()
                log_activity(
                    conn,
                    session.hero_name,
                    f"Quest {quest_id} blocked after {MAX_RESTARTS} restart attempts",
                    quest_id=quest_id,
                    level="error",
                )
            finally:
                conn.close()
            return

        # Check for recent commits to decide recovery strategy
        has_recent_commits = _check_recent_commits(session.project_path)

        conn = get_db()
        try:
            if has_recent_commits:
                # Has progress — recover with context
                print(f"  > {session.hero_name}: has recent commits, recovering with context")
                self._restart_counts[quest_id] = count + 1
                log_activity(
                    conn,
                    session.hero_name,
                    f"Recovering quest {quest_id} (attempt {count + 1}/{MAX_RESTARTS})",
                    quest_id=quest_id,
                )
            else:
                # No progress — reset quest to backlog
                print(f"  > {session.hero_name}: no recent commits, resetting quest to backlog")
                conn.execute(
                    "UPDATE quests SET status = 'backlog', assigned_to = NULL WHERE id = ?",
                    (quest_id,),
                )
                conn.execute(
                    "UPDATE heroes SET status = 'idle', current_quest_id = NULL WHERE id = ?",
                    (hero_id,),
                )
                conn.commit()
                log_activity(
                    conn,
                    session.hero_name,
                    f"Quest {quest_id} reset to backlog (no commits before crash)",
                    quest_id=quest_id,
                )
                return  # Don't re-spawn, quest needs re-assignment
        finally:
            conn.close()

        # Re-spawn with recovery context
        self.recover_hero(hero_id)


# --- Helper functions ---


def _check_recent_commits(project_path):
    """Check if there are recent commits (within last hour) at the project path."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1", "--since=1 hour ago"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _assemble_claude_md(hero_name, quest, project_name, output_path):
    """Assemble a basic CLAUDE.md for a hero session.

    In a full implementation, memory_manager would handle this.
    This is a fallback that creates a minimal working CLAUDE.md.
    """
    hero_memory_dir = MEMORY_DIR / "heroes" / hero_name

    # Try to load hero class template
    class_template = ""
    notes_content = ""
    shared_memory = ""

    notes_path = hero_memory_dir / "notes.md"
    if notes_path.exists():
        notes_content = notes_path.read_text().strip()

    shared_path = MEMORY_DIR / "shared" / "projects" / f"{project_name}.md"
    if shared_path.exists():
        shared_memory = shared_path.read_text().strip()

    content = f"# Hero: {hero_name}\n\n"

    if class_template:
        content += f"{class_template}\n\n"

    content += f"## Current Quest\n"
    content += f"- ID: {quest['id']}\n"
    content += f"- Title: {quest['title']}\n"
    if quest.get("branch"):
        content += f"- Branch: {quest['branch']}\n"
    content += f"- Project: {project_name}\n\n"

    if notes_content:
        content += f"## Hero Notes\n{notes_content}\n\n"

    if shared_memory:
        content += f"## Project Memory\n{shared_memory}\n\n"

    content += "## Rules\n"
    content += "- Commit often with message format: [GLD-{id}] description -- {hero_name}\n"
    content += "- Write completion report to workspace/outbox/{hero_name}.md when done\n"
    content += "- Update your notes in workspace/memory/heroes/{hero_name}/notes.md\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)


def _inject_recovery_context(hero_name, quest, project, claude_md_path):
    """Inject recovery context block into an existing CLAUDE.md."""
    project_path = Path(project["path"])

    # Get last commit info
    last_commit_hash = ""
    last_commit_msg = ""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.stdout.strip():
            parts = result.stdout.strip().split(" ", 1)
            last_commit_hash = parts[0]
            last_commit_msg = parts[1] if len(parts) > 1 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Get last activity log entry
    last_action = ""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT action FROM activity_log WHERE actor = ? ORDER BY timestamp DESC LIMIT 1",
            (hero_name,),
        ).fetchone()
        if row:
            last_action = row["action"]
    finally:
        conn.close()

    recovery_block = (
        "\n\n## RECOVERY CONTEXT\n"
        "Previous session ended unexpectedly.\n"
        f"Last known action: {last_action}\n"
        f"Last commit: {last_commit_hash} -- \"{last_commit_msg}\"\n"
        f"Quest status at crash: active\n\n"
        "Resume from last commit. Do not redo completed work.\n"
        "Run tests before continuing if unsure about state.\n"
    )

    # Read existing CLAUDE.md and append recovery block
    existing = ""
    if claude_md_path.exists():
        existing = claude_md_path.read_text()
        # Remove any previous recovery block
        if "## RECOVERY CONTEXT" in existing:
            idx = existing.index("## RECOVERY CONTEXT")
            existing = existing[:idx].rstrip()

    claude_md_path.write_text(existing + recovery_block)


def _resolve_hero_by_name(name):
    """Look up a hero by name, return the row or None."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, name, current_quest_id, status, session_pid FROM heroes WHERE name = ?",
            (name,),
        ).fetchone()
    finally:
        conn.close()


def main():
    """Standalone entry point: run a single hero session and monitor it."""
    parser = argparse.ArgumentParser(description="Guild Hero Runtime")
    parser.add_argument(
        "--hero",
        required=True,
        help="Hero name to start a session for",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=int,
        default=HEARTBEAT_INTERVAL,
        help=f"Heartbeat check interval in seconds (default: {HEARTBEAT_INTERVAL})",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print("Error: Guild not initialized. Run 'guild init' first.")
        return 1

    hero = _resolve_hero_by_name(args.hero)
    if not hero:
        print(f"Error: Hero '{args.hero}' not found")
        return 1

    if not hero["current_quest_id"]:
        print(f"Error: Hero '{args.hero}' has no assigned quest")
        return 1

    print(f"Hero Runtime: starting session for {args.hero}")
    print(f"  Quest: {hero['current_quest_id']}")
    print(f"  Heartbeat interval: {args.heartbeat_interval}s")
    print(f"  Press Ctrl+C to stop\n")

    manager = SessionManager()

    session = manager.start_hero(hero["id"])
    if not session:
        print("Error: Failed to start session")
        return 1

    try:
        while True:
            time.sleep(args.heartbeat_interval)
            manager.heartbeat()

            # If our session is gone (crashed and not recovered, or blocked), exit
            if hero["id"] not in manager.sessions:
                print(f"\nSession for {args.hero} is no longer active")
                break

            # Print status
            status = manager.get_status()
            hero_status = status.get(hero["id"])
            if hero_status:
                silence = hero_status.get("silence_seconds")
                state = hero_status.get("status")
                print(
                    f"  [{datetime.now().strftime('%H:%M:%S')}] "
                    f"{args.hero}: {state}, silence: {silence}s"
                )

    except KeyboardInterrupt:
        print(f"\nStopping session for {args.hero}...")
        manager.stop_all()
        print("Done.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
