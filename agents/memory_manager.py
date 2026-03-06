#!/usr/bin/env python3
"""
Memory Manager — handles persistent memory for the Guild system.

Manages shared project memory, hero notes/history, skill files,
ADR creation, learning classification, and auto-summarization.
"""

import json
import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic


GUILD_DIR = Path.home() / ".guild"
DB_PATH = GUILD_DIR / "guild.db"
MEMORY_DIR = GUILD_DIR / "workspace" / "memory"
SHARED_DIR = MEMORY_DIR / "shared"
HEROES_DIR = MEMORY_DIR / "heroes"
PROJECTS_DIR = SHARED_DIR / "projects"
CONVENTIONS_DIR = SHARED_DIR / "conventions"

AUTO_SUMMARIZE_THRESHOLD = 50 * 1024  # 50KB

CLASSIFY_SYSTEM_PROMPT = """\
You are a learning classifier for a software development guild system.

Given a list of learnings from a completed quest, classify each one into exactly one category:

- "architectural" — design decisions, system architecture choices, trade-offs, patterns adopted
- "project" — project-specific knowledge (API usage, config details, gotchas, conventions)
- "personal" — individual tips, workflow preferences, tool shortcuts, debugging techniques

Respond ONLY with valid JSON in this format:
{
  "classifications": [
    {"learning": "the learning text", "category": "architectural|project|personal"},
    ...
  ]
}
"""


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Read functions
# ---------------------------------------------------------------------------

def read_shared_memory(project_name):
    """Read shared project memory file."""
    path = PROJECTS_DIR / f"{project_name}.md"
    if not path.exists():
        return None
    return path.read_text()


def read_hero_notes(hero_name):
    """Read a hero's personal notes."""
    path = HEROES_DIR / hero_name / "notes.md"
    if not path.exists():
        return None
    return path.read_text()


def read_hero_history(hero_name):
    """Read a hero's quest history."""
    path = HEROES_DIR / hero_name / "history.md"
    if not path.exists():
        return None
    return path.read_text()


def read_skill_file(hero_name, skill_name):
    """Read a hero's skill backing file."""
    path = HEROES_DIR / hero_name / "skills" / f"{skill_name}.md"
    if not path.exists():
        return None
    return path.read_text()


def read_conventions():
    """Read all convention files from shared conventions directory."""
    if not CONVENTIONS_DIR.exists():
        return {}
    conventions = {}
    for f in CONVENTIONS_DIR.iterdir():
        if f.is_file():
            conventions[f.name] = f.read_text()
    return conventions


# ---------------------------------------------------------------------------
# Write functions
# ---------------------------------------------------------------------------

def _ensure_parent(path):
    """Ensure parent directory exists."""
    path.parent.mkdir(parents=True, exist_ok=True)


def append_shared_memory(project_name, content):
    """Append content to a project's shared memory file."""
    path = PROJECTS_DIR / f"{project_name}.md"
    _ensure_parent(path)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"\n---\n_Added: {timestamp}_\n{content}\n"
    with open(path, "a") as f:
        f.write(entry)
    check_and_summarize(path)


def update_hero_notes(hero_name, content):
    """Append content to a hero's notes file."""
    path = HEROES_DIR / hero_name / "notes.md"
    _ensure_parent(path)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"\n---\n_Added: {timestamp}_\n{content}\n"
    with open(path, "a") as f:
        f.write(entry)
    check_and_summarize(path)


def update_hero_history(hero_name, quest_id, summary):
    """Append a quest entry to a hero's history file."""
    path = HEROES_DIR / hero_name / "history.md"
    _ensure_parent(path)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"\n## {quest_id} -- {timestamp}\n{summary}\n"
    with open(path, "a") as f:
        f.write(entry)
    check_and_summarize(path)


def update_skill_file(hero_name, skill_name, content):
    """Write or update a hero's skill backing file."""
    path = HEROES_DIR / hero_name / "skills" / f"{skill_name}.md"
    _ensure_parent(path)
    path.write_text(content)


def create_adr(project_name, title, content):
    """Create an ADR file with auto-numbering."""
    adr_dir = SHARED_DIR / "adr" / project_name
    adr_dir.mkdir(parents=True, exist_ok=True)

    # Find next ADR number
    existing = sorted(adr_dir.glob("*.md"))
    next_num = 1
    if existing:
        for f in reversed(existing):
            match = re.match(r"(\d+)-", f.name)
            if match:
                next_num = int(match.group(1)) + 1
                break

    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    filename = f"{next_num:04d}-{slug}.md"
    path = adr_dir / filename

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    adr_content = f"# ADR-{next_num:04d}: {title}\n\n"
    adr_content += f"**Date:** {timestamp}\n\n"
    adr_content += f"**Status:** Accepted\n\n"
    adr_content += f"## Context\n\n{content}\n"

    path.write_text(adr_content)
    print(f"  + ADR: {filename}")
    return path


# ---------------------------------------------------------------------------
# Learning classification and routing
# ---------------------------------------------------------------------------

def route_learnings(hero_name, quest_id, learnings, project_name):
    """Classify and route learnings from a hero's completion report.

    Uses Claude API to classify each learning, then routes:
    - architectural -> create ADR
    - project -> append to shared project memory
    - personal -> append to hero notes
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ! Cannot route learnings: ANTHROPIC_API_KEY not set")
        return

    client = anthropic.Anthropic(api_key=api_key)

    prompt = (
        f"Hero: {hero_name}\n"
        f"Quest: {quest_id}\n"
        f"Project: {project_name}\n\n"
        f"Learnings:\n{learnings}\n"
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=CLASSIFY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text
        json_match = re.search(r'\{[\s\S]*\}', text)
        if not json_match:
            print("  ! Could not parse learning classifications")
            return

        data = json.loads(json_match.group())
        classifications = data.get("classifications", [])

        for item in classifications:
            learning = item.get("learning", "")
            category = item.get("category", "personal")

            if category == "architectural":
                # Extract a title from the learning (first sentence or first 60 chars)
                title_match = re.match(r"^(.{10,60}?)[\.\!\?]", learning)
                title = title_match.group(1) if title_match else learning[:60]
                create_adr(project_name, title, learning)
                print(f"  >> Architectural learning -> ADR")

            elif category == "project":
                append_shared_memory(project_name, f"**From {hero_name} ({quest_id}):**\n{learning}")
                print(f"  >> Project learning -> shared memory")

            elif category == "personal":
                update_hero_notes(hero_name, f"**Quest {quest_id}:**\n{learning}")
                print(f"  >> Personal learning -> hero notes")

        # Extract patterns to skill backing file
        conn = get_db()
        try:
            project_row = conn.execute("SELECT language FROM projects WHERE name = ?", (project_name,)).fetchone()
            skill_name = (project_row["language"] or project_name).lower().strip() if project_row else project_name.lower().strip()
        finally:
            conn.close()
        if skill_name:
            extract_patterns_to_skill(hero_name, skill_name, learnings)

    except Exception as e:
        print(f"  ! Failed to route learnings: {e}")


def extract_patterns_to_skill(hero_name, skill_name, learnings_text):
    """Extract patterns and gotchas from learnings and append to skill backing file."""
    if not learnings_text or not learnings_text.strip():
        return

    skill_file = HEROES_DIR / hero_name / "skills" / f"{skill_name}.md"
    if not skill_file.exists():
        return

    patterns = []
    for line in learnings_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        if any(kw in lower for kw in ['gotcha', 'pattern', 'tip', 'trick', 'important', 'note:', 'warning:', 'learned', 'discovered', 'found that', 'turns out']):
            patterns.append(line)

    if patterns:
        existing = skill_file.read_text()
        addition = f"\n\n## Patterns (auto-extracted)\n"
        for p in patterns:
            addition += f"- {p}\n"
        skill_file.write_text(existing + addition)
        print(f"  + Extracted {len(patterns)} pattern(s) to {hero_name}/{skill_name} skill file")


# ---------------------------------------------------------------------------
# Auto-summarization
# ---------------------------------------------------------------------------

def check_and_summarize(file_path):
    """If file exceeds threshold, archive it and summarize."""
    file_path = Path(file_path)
    if not file_path.exists():
        return

    size = file_path.stat().st_size
    if size <= AUTO_SUMMARIZE_THRESHOLD:
        return

    print(f"  ~ Auto-summarizing {file_path.name} ({size // 1024}KB > 50KB)")

    # Archive the full file
    archive_dir = file_path.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    archive_name = f"{date_str}-{file_path.name}"
    shutil.copy2(file_path, archive_dir / archive_name)

    # Summarize using Claude
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ! Cannot summarize: ANTHROPIC_API_KEY not set, file archived only")
        return

    content = file_path.read_text()
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=(
                "Summarize the following document into its key points. "
                "Keep only the most important information: decisions, patterns, "
                "critical learnings, and unresolved issues. "
                "Use markdown format with headers and bullet points."
            ),
            messages=[{"role": "user", "content": content}],
        )

        summary = response.content[0].text
        header = (
            f"# Summary (auto-generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')})\n"
            f"_Full history archived to: archive/{archive_name}_\n\n"
        )
        file_path.write_text(header + summary + "\n")
        print(f"  ~ Summarized {file_path.name}: {size // 1024}KB -> {len(header + summary) // 1024}KB")

    except Exception as e:
        print(f"  ! Summarization failed: {e} (original archived)")


# ---------------------------------------------------------------------------
# Proficiency tracking
# ---------------------------------------------------------------------------

def update_proficiency(hero_id, project_name):
    """Update hero proficiency level based on completed quest count.

    Proficiency levels:
      1-2 quests  -> level 1
      3-5 quests  -> level 2
      6-10 quests -> level 3
      11-20 quests -> level 4
      21+ quests  -> level 5

    At proficiency >= 4, extract key learnings to shared project memory.
    Also auto-creates a learned skill entry if none exists for the project's domain.
    """
    conn = get_db()

    # Resolve project
    project_row = conn.execute("SELECT id, language FROM projects WHERE name = ?", (project_name,)).fetchone()
    if not project_row:
        conn.close()
        return
    project_id = project_row["id"]

    # Resolve hero name
    hero_row = conn.execute("SELECT name FROM heroes WHERE id = ?", (hero_id,)).fetchone()
    hero_name = hero_row["name"] if hero_row else None

    # Auto-create skill for project domain if it doesn't exist
    skill_name = (project_row["language"] or project_name).lower().strip()
    if skill_name and hero_name:
        now = datetime.now(timezone.utc).isoformat()
        try:
            existing_skill = conn.execute(
                "SELECT id FROM hero_skills WHERE hero_id = ? AND name = ?",
                (hero_id, skill_name)
            ).fetchone()
            if not existing_skill:
                conn.execute(
                    "INSERT INTO hero_skills (id, hero_id, name, type, proficiency, source, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), hero_id, skill_name, "learned", 1, f"quest:{project_name}", now, now)
                )
                skill_dir = HEROES_DIR / hero_name / "skills"
                skill_dir.mkdir(parents=True, exist_ok=True)
                skill_file = skill_dir / f"{skill_name}.md"
                if not skill_file.exists():
                    skill_file.write_text(f"# {skill_name}\n\nLearned from working on {project_name}.\n")
                print(f"  + Auto-created skill '{skill_name}' for {hero_name}")
        except sqlite3.OperationalError:
            pass

    # Count completed quests for this hero + project
    count_row = conn.execute(
        "SELECT COUNT(*) as cnt FROM quests "
        "WHERE assigned_to = ? AND project_id = ? AND status = 'done'",
        (hero_id, project_id),
    ).fetchone()
    quest_count = count_row["cnt"] if count_row else 0

    # Determine proficiency level
    if quest_count >= 21:
        prof_level = 5
    elif quest_count >= 11:
        prof_level = 4
    elif quest_count >= 6:
        prof_level = 3
    elif quest_count >= 3:
        prof_level = 2
    else:
        prof_level = 1

    # Upsert proficiency (try to update, then insert if needed)
    existing = conn.execute(
        "SELECT level FROM hero_proficiency WHERE hero_id = ? AND project_id = ?",
        (hero_id, project_id),
    ).fetchone()

    try:
        if existing:
            old_level = existing["level"]
            if prof_level != old_level:
                conn.execute(
                    "UPDATE hero_proficiency SET level = ?, quest_count = ? WHERE hero_id = ? AND project_id = ?",
                    (prof_level, quest_count, hero_id, project_id),
                )
        else:
            conn.execute(
                "INSERT INTO hero_proficiency (id, hero_id, project_id, level, quest_count) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), hero_id, project_id, prof_level, quest_count),
            )
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # At proficiency >= 4, extract key learnings to shared memory
    if prof_level >= 4 and (not existing or existing["level"] < 4):
        if hero_name:
            notes = read_hero_notes(hero_name)
            if notes:
                append_shared_memory(
                    project_name,
                    f"**Expert learnings from {hero_name} (proficiency level {prof_level}):**\n"
                    f"(Auto-extracted at proficiency threshold)\n\n{notes[:2000]}",
                )
                print(f"  ~ Extracted expert learnings from {hero_name} to shared memory")

    conn.close()
    return prof_level
