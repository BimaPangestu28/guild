import unittest
import sqlite3
import tempfile
import os
import sys
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestIntegrationFlow(unittest.TestCase):
    def setUp(self):
        """Set up a temporary guild environment."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "guild.db")

        # Create tables (copy the schema from db creation)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._setup_dirs()

    def _create_tables(self):
        """Create all guild tables."""
        self.conn.executescript("""
            CREATE TABLE heroes (id TEXT PRIMARY KEY, name TEXT, class TEXT, status TEXT DEFAULT 'offline', level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, current_quest_id TEXT, session_pid INTEGER, last_active TEXT);
            CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT, display_name TEXT, path TEXT, repo_url TEXT, repo_provider TEXT DEFAULT 'none', main_branch TEXT DEFAULT 'main', dev_branch TEXT DEFAULT 'development', language TEXT, status TEXT DEFAULT 'active', default_mcps TEXT, created_at TEXT, last_active TEXT);
            CREATE TABLE quest_chains (id TEXT PRIMARY KEY, goal TEXT, project_id TEXT, status TEXT DEFAULT 'active', created_at TEXT, completed_at TEXT);
            CREATE TABLE quests (id TEXT PRIMARY KEY, chain_id TEXT, parent_quest_id TEXT, title TEXT, description TEXT, tier TEXT, type TEXT, status TEXT DEFAULT 'backlog', project_id TEXT, branch TEXT, req_skills TEXT, assigned_to TEXT, result TEXT, created_at TEXT, completed_at TEXT);
            CREATE TABLE hero_skills (id TEXT PRIMARY KEY, hero_id TEXT, name TEXT, type TEXT, proficiency INTEGER DEFAULT 1, source TEXT, created_at TEXT, updated_at TEXT);
            CREATE TABLE activity_log (id TEXT PRIMARY KEY, timestamp TEXT, actor TEXT, action TEXT, quest_id TEXT, project_id TEXT, level TEXT DEFAULT 'info');
            CREATE TABLE cost_log (id TEXT PRIMARY KEY, timestamp TEXT DEFAULT (datetime('now')), actor TEXT, category TEXT, project_id TEXT, quest_id TEXT, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0.0, model TEXT, note TEXT);
            CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT);
        """)
        self.conn.commit()

    def _setup_dirs(self):
        """Create directory structure."""
        for d in ["workspace/inbox", "workspace/outbox", "workspace/quests/backlog",
                   "workspace/quests/active", "workspace/quests/done",
                   "workspace/memory/shared", "workspace/memory/heroes"]:
            os.makedirs(os.path.join(self.tmpdir, d), exist_ok=True)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_goal_to_quest_chain(self):
        """Test that a goal creates quest chains with proper structure."""
        now = datetime.now(timezone.utc).isoformat()

        # Insert a project
        self.conn.execute(
            "INSERT INTO projects (id, name, display_name, path, language, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "test-project", "Test Project", self.tmpdir, "python", now)
        )

        # Insert a hero with skills
        hero_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO heroes (id, name, class, status) VALUES (?, ?, ?, ?)",
            (hero_id, "TestHero", "Python Paladin", "idle")
        )
        self.conn.execute(
            "INSERT INTO hero_skills (id, hero_id, name, type, proficiency) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), hero_id, "python", "base", 3)
        )
        self.conn.commit()

        # Simulate quest chain creation (what guild_master does after decomposing a goal)
        chain_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO quest_chains (id, goal, project_id, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (chain_id, "Add user authentication", "test-project", "active", now)
        )

        quest_id = f"GLD-{uuid.uuid4().hex[:6].upper()}"
        self.conn.execute(
            "INSERT INTO quests (id, chain_id, title, description, tier, type, status, project_id, req_skills, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (quest_id, chain_id, "Implement user auth", "Add login/register endpoints", "RARE", "feature", "backlog", "test-project", "python", now)
        )
        self.conn.commit()

        # Verify chain exists
        chain = self.conn.execute("SELECT * FROM quest_chains WHERE id = ?", (chain_id,)).fetchone()
        self.assertEqual(chain["status"], "active")

        # Verify quest exists
        quest = self.conn.execute("SELECT * FROM quests WHERE id = ?", (quest_id,)).fetchone()
        self.assertEqual(quest["status"], "backlog")
        self.assertEqual(quest["chain_id"], chain_id)

    def test_quest_assignment_to_hero(self):
        """Test that a quest can be assigned to a matching hero."""
        now = datetime.now(timezone.utc).isoformat()

        # Create hero
        hero_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO heroes (id, name, class, status) VALUES (?, ?, ?, ?)",
            (hero_id, "AssignHero", "Rust Sorcerer", "idle")
        )
        self.conn.execute(
            "INSERT INTO hero_skills (id, hero_id, name, type, proficiency) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), hero_id, "rust", "base", 2)
        )

        # Create quest
        quest_id = f"GLD-{uuid.uuid4().hex[:6].upper()}"
        self.conn.execute(
            "INSERT INTO quests (id, chain_id, title, tier, type, status, req_skills, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (quest_id, "chain1", "Build parser", "COMMON", "feature", "backlog", "rust", now)
        )
        self.conn.commit()

        # Simulate assignment (what find_best_hero + assign does)
        self.conn.execute("UPDATE quests SET status = 'active', assigned_to = ? WHERE id = ?", (hero_id, quest_id))
        self.conn.execute("UPDATE heroes SET status = 'on_quest', current_quest_id = ? WHERE id = ?", (quest_id, hero_id))
        self.conn.commit()

        hero = self.conn.execute("SELECT * FROM heroes WHERE id = ?", (hero_id,)).fetchone()
        self.assertEqual(hero["status"], "on_quest")
        self.assertEqual(hero["current_quest_id"], quest_id)

        quest = self.conn.execute("SELECT * FROM quests WHERE id = ?", (quest_id,)).fetchone()
        self.assertEqual(quest["status"], "active")
        self.assertEqual(quest["assigned_to"], hero_id)

    def test_quest_completion_flow(self):
        """Test quest completion updates hero XP and status."""
        now = datetime.now(timezone.utc).isoformat()

        hero_id = str(uuid.uuid4())
        quest_id = "GLD-TEST01"
        chain_id = str(uuid.uuid4())

        self.conn.execute(
            "INSERT INTO heroes (id, name, class, status, level, xp, current_quest_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (hero_id, "CompHero", "TypeScript Templar", "on_quest", 1, 0, quest_id)
        )
        self.conn.execute(
            "INSERT INTO quest_chains (id, goal, status, created_at) VALUES (?, ?, ?, ?)",
            (chain_id, "Test goal", "active", now)
        )
        self.conn.execute(
            "INSERT INTO quests (id, chain_id, title, tier, type, status, assigned_to, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (quest_id, chain_id, "Test quest", "COMMON", "feature", "active", hero_id, now)
        )
        self.conn.commit()

        # Simulate completion
        xp_rewards = {"COMMON": 100, "RARE": 250, "EPIC": 500}
        xp_gain = xp_rewards.get("COMMON", 100)

        self.conn.execute("UPDATE quests SET status = 'done', completed_at = ? WHERE id = ?", (now, quest_id))
        self.conn.execute("UPDATE heroes SET xp = xp + ?, status = 'idle', current_quest_id = NULL WHERE id = ?", (xp_gain, hero_id))
        self.conn.commit()

        hero = self.conn.execute("SELECT * FROM heroes WHERE id = ?", (hero_id,)).fetchone()
        self.assertEqual(hero["status"], "idle")
        self.assertEqual(hero["xp"], 100)
        self.assertIsNone(hero["current_quest_id"])

        quest = self.conn.execute("SELECT * FROM quests WHERE id = ?", (quest_id,)).fetchone()
        self.assertEqual(quest["status"], "done")

    def test_cost_tracking(self):
        """Test cost logging and daily totals."""
        # Log some costs
        for i in range(3):
            self.conn.execute(
                "INSERT INTO cost_log (id, actor, category, input_tokens, output_tokens, cost_usd, model) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), "guild_master", "guild_master", 1000, 500, 0.05, "claude-sonnet-4-20250514")
            )
        self.conn.commit()

        # Check totals
        row = self.conn.execute("SELECT SUM(cost_usd) as total, SUM(input_tokens) as inp, SUM(output_tokens) as out FROM cost_log WHERE date(timestamp) = date('now')").fetchone()
        self.assertAlmostEqual(row["total"], 0.15, places=2)
        self.assertEqual(row["inp"], 3000)
        self.assertEqual(row["out"], 1500)

    def test_activity_logging(self):
        """Test activity log entries."""
        now = datetime.now(timezone.utc).isoformat()

        self.conn.execute(
            "INSERT INTO activity_log (id, timestamp, actor, action, level) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), now, "guild-master", "Assigned quest GLD-001 to TestHero", "info")
        )
        self.conn.commit()

        logs = self.conn.execute("SELECT * FROM activity_log ORDER BY timestamp DESC").fetchall()
        self.assertEqual(len(logs), 1)
        self.assertIn("GLD-001", logs[0]["action"])


if __name__ == "__main__":
    unittest.main()
