use anyhow::{Context, Result};
use rusqlite::Connection;
use std::path::{Path, PathBuf};

pub fn guild_dir() -> PathBuf {
    dirs::home_dir()
        .expect("Cannot find home directory")
        .join(".guild")
}

pub fn db_path() -> PathBuf {
    guild_dir().join("guild.db")
}

pub fn open() -> Result<Connection> {
    let path = db_path();
    let conn = Connection::open(&path)
        .with_context(|| format!("Failed to open database at {}", path.display()))?;
    conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")?;
    Ok(conn)
}

pub fn init_at(path: &Path) -> Result<Connection> {
    let conn = Connection::open(path)
        .with_context(|| format!("Failed to create database at {}", path.display()))?;
    conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")?;
    create_tables(&conn)?;
    Ok(conn)
}

fn create_tables(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS heroes (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL UNIQUE,
            class           TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'offline',
            level           INTEGER NOT NULL DEFAULT 1,
            xp              INTEGER NOT NULL DEFAULT 0,
            current_quest_id TEXT,
            session_pid     INTEGER,
            last_active     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL UNIQUE,
            display_name    TEXT NOT NULL,
            path            TEXT NOT NULL,
            repo_url        TEXT,
            repo_provider   TEXT,
            main_branch     TEXT NOT NULL DEFAULT 'main',
            dev_branch      TEXT NOT NULL DEFAULT 'development',
            language        TEXT,
            status          TEXT NOT NULL DEFAULT 'active',
            default_mcps    TEXT NOT NULL DEFAULT '[]',
            created_at      TEXT NOT NULL,
            last_active     TEXT
        );

        CREATE TABLE IF NOT EXISTS project_groups (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL UNIQUE,
            created_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS project_group_members (
            group_id        TEXT NOT NULL REFERENCES project_groups(id),
            project_id      TEXT NOT NULL REFERENCES projects(id),
            PRIMARY KEY (group_id, project_id)
        );

        CREATE TABLE IF NOT EXISTS quest_chains (
            id              TEXT PRIMARY KEY,
            goal            TEXT NOT NULL,
            project_id      TEXT NOT NULL REFERENCES projects(id),
            status          TEXT NOT NULL DEFAULT 'active',
            created_at      TEXT NOT NULL,
            completed_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS quests (
            id              TEXT PRIMARY KEY,
            chain_id        TEXT NOT NULL REFERENCES quest_chains(id),
            parent_quest_id TEXT,
            title           TEXT NOT NULL,
            description     TEXT NOT NULL,
            tier            TEXT NOT NULL,
            type            TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'backlog',
            project_id      TEXT NOT NULL REFERENCES projects(id),
            branch          TEXT NOT NULL,
            req_skills      TEXT NOT NULL DEFAULT '[]',
            assigned_to     TEXT,
            result          TEXT,
            created_at      TEXT NOT NULL,
            completed_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS hero_skills (
            id              TEXT PRIMARY KEY,
            hero_id         TEXT NOT NULL REFERENCES heroes(id),
            name            TEXT NOT NULL,
            type            TEXT NOT NULL,
            proficiency     INTEGER NOT NULL DEFAULT 1,
            source          TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mcp_servers (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            display_name    TEXT NOT NULL,
            url             TEXT,
            command         TEXT,
            args            TEXT,
            env_vars        TEXT,
            skills_served   TEXT NOT NULL DEFAULT '[]',
            status          TEXT NOT NULL DEFAULT 'active',
            added_at        TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS hero_mcps (
            hero_id         TEXT NOT NULL REFERENCES heroes(id),
            mcp_id          TEXT NOT NULL REFERENCES mcp_servers(id),
            auto_attach     INTEGER NOT NULL DEFAULT 0,
            added_at        TEXT NOT NULL,
            PRIMARY KEY (hero_id, mcp_id)
        );

        CREATE TABLE IF NOT EXISTS file_locks (
            file_path       TEXT PRIMARY KEY,
            quest_id        TEXT NOT NULL,
            hero_id         TEXT NOT NULL,
            locked_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memories (
            id              TEXT PRIMARY KEY,
            owner           TEXT NOT NULL,
            project_id      TEXT,
            category        TEXT NOT NULL,
            content         TEXT NOT NULL,
            tags            TEXT NOT NULL DEFAULT '[]',
            created_by      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id              TEXT PRIMARY KEY,
            timestamp       TEXT NOT NULL,
            actor           TEXT NOT NULL,
            action          TEXT NOT NULL,
            quest_id        TEXT,
            project_id      TEXT,
            level           TEXT NOT NULL DEFAULT 'info'
        );
        ",
    )?;
    Ok(())
}

pub fn log_activity(
    conn: &Connection,
    actor: &str,
    action: &str,
    quest_id: Option<&str>,
    project_id: Option<&str>,
    level: &str,
) -> Result<()> {
    let id = uuid::Uuid::new_v4().to_string();
    let now = chrono::Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO activity_log (id, timestamp, actor, action, quest_id, project_id, level) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
        rusqlite::params![id, now, actor, action, quest_id, project_id, level],
    )?;
    Ok(())
}
