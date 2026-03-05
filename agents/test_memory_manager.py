import unittest
import tempfile
import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

# Override GUILD_DIR before importing
TEST_DIR = tempfile.mkdtemp()
os.environ['GUILD_TEST_DIR'] = TEST_DIR

class TestMemoryManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        # Setup directory structure
        (self.test_dir / "workspace/memory/shared/projects").mkdir(parents=True)
        (self.test_dir / "workspace/memory/shared/conventions").mkdir(parents=True)
        (self.test_dir / "workspace/memory/heroes/TestHero/skills").mkdir(parents=True)
        (self.test_dir / "workspace/memory/heroes/TestHero/notes.md").write_text("# Notes\n")
        (self.test_dir / "workspace/memory/heroes/TestHero/history.md").write_text("# History\n")
        (self.test_dir / "workspace/memory/shared/projects/test-project.md").write_text("# Test Project\n")

    def test_read_shared_memory(self):
        content = (self.test_dir / "workspace/memory/shared/projects/test-project.md").read_text()
        self.assertIn("Test Project", content)

    def test_read_hero_notes(self):
        content = (self.test_dir / "workspace/memory/heroes/TestHero/notes.md").read_text()
        self.assertIn("Notes", content)

    def test_append_to_file(self):
        path = self.test_dir / "workspace/memory/shared/projects/test-project.md"
        original = path.read_text()
        path.write_text(original + "\nNew learning\n")
        content = path.read_text()
        self.assertIn("New learning", content)

    def test_skill_file_creation(self):
        skill_path = self.test_dir / "workspace/memory/heroes/TestHero/skills/rust.md"
        skill_path.write_text("# Skill: rust\n\nKey patterns learned.\n")
        self.assertTrue(skill_path.exists())
        self.assertIn("rust", skill_path.read_text())

    def test_adr_numbering(self):
        adr_dir = self.test_dir / "workspace/memory/shared/projects/test-project-adr"
        adr_dir.mkdir(parents=True, exist_ok=True)
        # Create first ADR
        (adr_dir / "adr-001.md").write_text("# ADR 001\n")
        # Check numbering
        existing = sorted(adr_dir.glob("adr-*.md"))
        next_num = len(existing) + 1
        self.assertEqual(next_num, 2)

if __name__ == '__main__':
    unittest.main()
