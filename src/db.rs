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

        CREATE TABLE IF NOT EXISTS cost_log (
            id              TEXT PRIMARY KEY,
            timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
            actor           TEXT NOT NULL,
            category        TEXT NOT NULL,
            project_id      TEXT,
            quest_id        TEXT,
            input_tokens    INTEGER NOT NULL DEFAULT 0,
            output_tokens   INTEGER NOT NULL DEFAULT 0,
            cost_usd        REAL NOT NULL DEFAULT 0.0,
            model           TEXT,
            note            TEXT
        );

        CREATE TABLE IF NOT EXISTS config (
            key             TEXT PRIMARY KEY,
            value           TEXT NOT NULL
        );
        ",
    )?;
    Ok(())
}

/// Lock files for a quest/hero
pub fn lock_files(conn: &Connection, files: &[&str], quest_id: &str, hero_id: &str) -> Result<Vec<String>> {
    let now = chrono::Utc::now().to_rfc3339();
    let mut conflicts = vec![];
    for file in files {
        // Check if already locked by another quest
        let existing: Option<(String, String)> = conn.query_row(
            "SELECT quest_id, hero_id FROM file_locks WHERE file_path = ?1",
            [file],
            |row| Ok((row.get(0)?, row.get(1)?))
        ).ok();

        if let Some((existing_quest, _)) = existing {
            if existing_quest != quest_id {
                conflicts.push(format!("{} (locked by quest {})", file, existing_quest));
                continue;
            }
        }

        conn.execute(
            "INSERT OR REPLACE INTO file_locks (file_path, quest_id, hero_id, locked_at) VALUES (?1, ?2, ?3, ?4)",
            rusqlite::params![file, quest_id, hero_id, now],
        )?;
    }
    Ok(conflicts)
}

/// Release all locks for a quest
pub fn release_locks(conn: &Connection, quest_id: &str) -> Result<usize> {
    let count = conn.execute("DELETE FROM file_locks WHERE quest_id = ?1", [quest_id])?;
    Ok(count)
}

/// Get all current file locks
pub fn get_locks(conn: &Connection) -> Result<Vec<(String, String, String, String)>> {
    let mut stmt = conn.prepare(
        "SELECT f.file_path, f.quest_id, h.name, f.locked_at FROM file_locks f JOIN heroes h ON f.hero_id = h.id ORDER BY f.locked_at"
    )?;
    let rows = stmt.query_map([], |row| {
        Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?))
    })?;
    rows.collect::<std::result::Result<Vec<_>, _>>().map_err(|e| e.into())
}

/// Create a backup of the database
pub fn backup() -> Result<String> {
    let db = db_path();
    if !db.exists() {
        anyhow::bail!("Database not found");
    }

    let backup_dir = guild_dir().join("backups");
    std::fs::create_dir_all(&backup_dir)?;

    let timestamp = chrono::Utc::now().format("%Y%m%d-%H%M%S");
    let backup_name = format!("guild-{}.db", timestamp);
    let backup_path = backup_dir.join(&backup_name);

    std::fs::copy(&db, &backup_path)?;

    // Retain only last 24 backups
    let mut backups: Vec<_> = std::fs::read_dir(&backup_dir)?
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().map(|x| x == "db").unwrap_or(false))
        .collect();
    backups.sort_by_key(|e| e.path());

    while backups.len() > 24 {
        if let Some(oldest) = backups.first() {
            let _ = std::fs::remove_file(oldest.path());
        }
        backups.remove(0);
    }

    Ok(backup_name)
}

/// List available backups
pub fn list_backups() -> Result<Vec<(String, u64)>> {
    let backup_dir = guild_dir().join("backups");
    if !backup_dir.exists() {
        return Ok(vec![]);
    }

    let mut backups: Vec<(String, u64)> = std::fs::read_dir(&backup_dir)?
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().map(|x| x == "db").unwrap_or(false))
        .map(|e| {
            let size = e.metadata().map(|m| m.len()).unwrap_or(0);
            (e.file_name().to_string_lossy().to_string(), size)
        })
        .collect();
    backups.sort();
    Ok(backups)
}

/// Restore from a backup
pub fn restore_backup(filename: &str) -> Result<()> {
    let backup_dir = guild_dir().join("backups");
    let backup_path = backup_dir.join(filename);

    if !backup_path.exists() {
        anyhow::bail!("Backup '{}' not found", filename);
    }

    let db = db_path();

    // Create a safety backup of current DB first
    if db.exists() {
        let safety = backup_dir.join("pre-restore.db");
        std::fs::copy(&db, &safety)?;
    }

    std::fs::copy(&backup_path, &db)?;
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

pub fn get_config(conn: &Connection, key: &str) -> Result<Option<String>> {
    let result: Option<String> = conn
        .query_row(
            "SELECT value FROM config WHERE key = ?1",
            [key],
            |row| row.get(0),
        )
        .ok();
    Ok(result)
}

pub fn set_config(conn: &Connection, key: &str, value: &str) -> Result<()> {
    conn.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?1, ?2)",
        rusqlite::params![key, value],
    )?;
    Ok(())
}

#[allow(clippy::too_many_arguments)]
pub fn log_cost(
    conn: &Connection,
    actor: &str,
    category: &str,
    project_id: Option<&str>,
    quest_id: Option<&str>,
    input_tokens: i64,
    output_tokens: i64,
    cost_usd: f64,
    model: Option<&str>,
    note: Option<&str>,
) -> Result<()> {
    let id = uuid::Uuid::new_v4().to_string();
    conn.execute(
        "INSERT INTO cost_log (id, actor, category, project_id, quest_id, input_tokens, output_tokens, cost_usd, model, note) \
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
        rusqlite::params![id, actor, category, project_id, quest_id, input_tokens, output_tokens, cost_usd, model, note],
    )?;
    Ok(())
}

pub fn get_cost_today(conn: &Connection) -> Result<(f64, i64, i64)> {
    let row = conn.query_row(
        "SELECT COALESCE(SUM(cost_usd), 0.0), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0) \
         FROM cost_log WHERE date(timestamp) = date('now')",
        [],
        |row| Ok((row.get::<_, f64>(0)?, row.get::<_, i64>(1)?, row.get::<_, i64>(2)?)),
    )?;
    Ok(row)
}

pub fn get_cost_by_actor(conn: &Connection, date: &str) -> Result<Vec<(String, f64)>> {
    let mut stmt = conn.prepare(
        "SELECT actor, COALESCE(SUM(cost_usd), 0.0) FROM cost_log WHERE date(timestamp) = ?1 GROUP BY actor ORDER BY SUM(cost_usd) DESC",
    )?;
    let rows = stmt.query_map([date], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, f64>(1)?))
    })?;
    rows.collect::<std::result::Result<Vec<_>, _>>().map_err(|e| e.into())
}

pub fn get_cost_by_project(conn: &Connection, date: &str) -> Result<Vec<(String, f64)>> {
    let mut stmt = conn.prepare(
        "SELECT COALESCE(p.name, 'unknown'), COALESCE(SUM(c.cost_usd), 0.0) \
         FROM cost_log c LEFT JOIN projects p ON c.project_id = p.id \
         WHERE date(c.timestamp) = ?1 AND c.project_id IS NOT NULL \
         GROUP BY c.project_id ORDER BY SUM(c.cost_usd) DESC",
    )?;
    let rows = stmt.query_map([date], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, f64>(1)?))
    })?;
    rows.collect::<std::result::Result<Vec<_>, _>>().map_err(|e| e.into())
}

// --- Hero CRUD ---

pub fn get_hero_by_name(conn: &Connection, name: &str) -> Result<Option<(String, String, String, String, i64, i64, Option<String>)>> {
    let mut stmt = conn.prepare("SELECT id, name, class, status, level, xp, current_quest_id FROM heroes WHERE name = ?1")?;
    let result = stmt.query_row([name], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, i64>(4)?,
            row.get::<_, i64>(5)?,
            row.get::<_, Option<String>>(6)?,
        ))
    });
    match result {
        Ok(r) => Ok(Some(r)),
        Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
        Err(e) => Err(e.into()),
    }
}

pub fn update_hero_status(conn: &Connection, name: &str, status: &str) -> Result<()> {
    conn.execute("UPDATE heroes SET status = ?1 WHERE name = ?2", rusqlite::params![status, name])?;
    Ok(())
}

pub fn delete_hero(conn: &Connection, name: &str) -> Result<()> {
    let hero_id: Option<String> = conn
        .query_row("SELECT id FROM heroes WHERE name = ?1", [name], |row| row.get(0))
        .ok();
    if let Some(id) = hero_id {
        conn.execute("DELETE FROM hero_skills WHERE hero_id = ?1", [&id])?;
        conn.execute("DELETE FROM heroes WHERE id = ?1", [&id])?;
    }
    Ok(())
}

// --- Quest CRUD ---

pub fn get_quest(conn: &Connection, id: &str) -> Result<Option<(String, String, String, String, String, Option<String>)>> {
    let mut stmt = conn.prepare("SELECT id, title, status, type, tier, assigned_to FROM quests WHERE id = ?1")?;
    let result = stmt.query_row([id], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, Option<String>>(5)?,
        ))
    });
    match result {
        Ok(r) => Ok(Some(r)),
        Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
        Err(e) => Err(e.into()),
    }
}

pub fn update_quest_status(conn: &Connection, id: &str, status: &str) -> Result<()> {
    conn.execute("UPDATE quests SET status = ?1 WHERE id = ?2", rusqlite::params![status, id])?;
    if status == "done" {
        let now = chrono::Utc::now().to_rfc3339();
        conn.execute("UPDATE quests SET completed_at = ?1 WHERE id = ?2", rusqlite::params![now, id])?;
    }
    Ok(())
}

pub fn list_quests_by_status(conn: &Connection, status: &str) -> Result<Vec<(String, String, String, Option<String>)>> {
    let mut stmt = conn.prepare("SELECT id, title, tier, assigned_to FROM quests WHERE status = ?1 ORDER BY created_at")?;
    let rows = stmt.query_map([status], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, Option<String>>(3)?,
        ))
    })?;
    rows.collect::<std::result::Result<Vec<_>, _>>().map_err(|e| e.into())
}

// --- Project CRUD ---

pub fn get_project_by_name(conn: &Connection, name: &str) -> Result<Option<(String, String, String, String, String, String)>> {
    let mut stmt = conn.prepare("SELECT id, name, path, repo_provider, main_branch, dev_branch FROM projects WHERE name = ?1")?;
    let result = stmt.query_row([name], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, String>(5)?,
        ))
    });
    match result {
        Ok(r) => Ok(Some(r)),
        Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
        Err(e) => Err(e.into()),
    }
}

pub fn update_project_status(conn: &Connection, name: &str, status: &str) -> Result<()> {
    conn.execute("UPDATE projects SET status = ?1 WHERE name = ?2", rusqlite::params![status, name])?;
    Ok(())
}

// --- Activity Log ---

pub fn get_recent_activity(conn: &Connection, limit: usize) -> Result<Vec<(String, String, String, String)>> {
    let mut stmt = conn.prepare("SELECT timestamp, actor, action, level FROM activity_log ORDER BY timestamp DESC LIMIT ?1")?;
    let rows = stmt.query_map([limit], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
        ))
    })?;
    rows.collect::<std::result::Result<Vec<_>, _>>().map_err(|e| e.into())
}

pub fn get_cost_daily_cap(conn: &Connection) -> f64 {
    get_config(conn, "cost-cap-daily")
        .ok()
        .flatten()
        .and_then(|v| v.parse::<f64>().ok())
        .unwrap_or(10.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_db() -> Connection {
        let conn = Connection::open_in_memory().unwrap();
        conn.execute_batch("PRAGMA foreign_keys=ON;").unwrap();
        create_tables(&conn).unwrap();
        conn
    }

    #[test]
    fn test_create_tables() {
        let conn = test_db();
        // Verify all tables exist
        let tables: Vec<String> = conn.prepare(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).unwrap()
        .query_map([], |row| row.get(0)).unwrap()
        .filter_map(|r| r.ok()).collect();

        assert!(tables.contains(&"heroes".to_string()));
        assert!(tables.contains(&"projects".to_string()));
        assert!(tables.contains(&"quests".to_string()));
        assert!(tables.contains(&"quest_chains".to_string()));
        assert!(tables.contains(&"hero_skills".to_string()));
        assert!(tables.contains(&"activity_log".to_string()));
        assert!(tables.contains(&"file_locks".to_string()));
        assert!(tables.contains(&"memories".to_string()));
        assert!(tables.contains(&"mcp_servers".to_string()));
        assert!(tables.contains(&"cost_log".to_string()));
        assert!(tables.contains(&"config".to_string()));
    }

    #[test]
    fn test_log_activity() {
        let conn = test_db();
        log_activity(&conn, "test", "test action", None, None, "info").unwrap();

        let count: i32 = conn.query_row(
            "SELECT COUNT(*) FROM activity_log", [], |r| r.get(0)
        ).unwrap();
        assert_eq!(count, 1);

        let action: String = conn.query_row(
            "SELECT action FROM activity_log", [], |r| r.get(0)
        ).unwrap();
        assert_eq!(action, "test action");
    }

    #[test]
    fn test_lock_files() {
        let conn = test_db();

        // Insert a hero first
        conn.execute(
            "INSERT INTO heroes (id, name, class, status, level, xp, last_active) VALUES ('h1', 'TestHero', 'Rust Sorcerer', 'idle', 1, 0, '2024-01-01')",
            [],
        ).unwrap();

        let conflicts = lock_files(&conn, &["src/main.rs", "src/lib.rs"], "q1", "h1").unwrap();
        assert!(conflicts.is_empty());

        // Lock same files with different quest should conflict
        let conflicts = lock_files(&conn, &["src/main.rs"], "q2", "h1").unwrap();
        assert_eq!(conflicts.len(), 1);
        assert!(conflicts[0].contains("src/main.rs"));

        // Release locks
        let released = release_locks(&conn, "q1").unwrap();
        assert_eq!(released, 2);

        // Now should work
        let conflicts = lock_files(&conn, &["src/main.rs"], "q2", "h1").unwrap();
        assert!(conflicts.is_empty());
    }

    #[test]
    fn test_get_locks() {
        let conn = test_db();
        conn.execute(
            "INSERT INTO heroes (id, name, class, status, level, xp, last_active) VALUES ('h1', 'TestHero', 'Rust Sorcerer', 'idle', 1, 0, '2024-01-01')",
            [],
        ).unwrap();

        lock_files(&conn, &["file1.rs"], "q1", "h1").unwrap();
        let locks = get_locks(&conn).unwrap();
        assert_eq!(locks.len(), 1);
        assert_eq!(locks[0].0, "file1.rs");
    }

    fn insert_test_hero(conn: &Connection, id: &str, name: &str) {
        conn.execute(
            "INSERT INTO heroes (id, name, class, status, level, xp, last_active) VALUES (?1, ?2, 'Rust Sorcerer', 'idle', 1, 0, '2024-01-01')",
            rusqlite::params![id, name],
        ).unwrap();
    }

    fn insert_test_project(conn: &Connection, id: &str, name: &str) {
        let now = chrono::Utc::now().to_rfc3339();
        conn.execute(
            "INSERT INTO projects (id, name, display_name, path, repo_provider, main_branch, dev_branch, status, created_at) VALUES (?1, ?2, ?2, '/tmp/test', 'none', 'main', 'development', 'active', ?3)",
            rusqlite::params![id, name, now],
        ).unwrap();
    }

    #[test]
    fn test_get_hero_by_name() {
        let conn = test_db();
        insert_test_hero(&conn, "h1", "Aria");

        let hero = get_hero_by_name(&conn, "Aria").unwrap();
        assert!(hero.is_some());
        let (id, name, class, status, level, xp, quest) = hero.unwrap();
        assert_eq!(id, "h1");
        assert_eq!(name, "Aria");
        assert_eq!(class, "Rust Sorcerer");
        assert_eq!(status, "idle");
        assert_eq!(level, 1);
        assert_eq!(xp, 0);
        assert!(quest.is_none());

        let missing = get_hero_by_name(&conn, "NonExistent").unwrap();
        assert!(missing.is_none());
    }

    #[test]
    fn test_update_hero_status() {
        let conn = test_db();
        insert_test_hero(&conn, "h1", "Aria");

        update_hero_status(&conn, "Aria", "active").unwrap();

        let hero = get_hero_by_name(&conn, "Aria").unwrap().unwrap();
        assert_eq!(hero.3, "active");
    }

    #[test]
    fn test_delete_hero() {
        let conn = test_db();
        insert_test_hero(&conn, "h1", "Aria");
        conn.execute(
            "INSERT INTO hero_skills (id, hero_id, name, type, proficiency, created_at, updated_at) VALUES ('s1', 'h1', 'rust', 'language', 3, '2024-01-01', '2024-01-01')",
            [],
        ).unwrap();

        delete_hero(&conn, "Aria").unwrap();

        let hero = get_hero_by_name(&conn, "Aria").unwrap();
        assert!(hero.is_none());

        let skill_count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM hero_skills WHERE hero_id = 'h1'", [], |r| r.get(0)
        ).unwrap();
        assert_eq!(skill_count, 0);
    }

    #[test]
    fn test_get_quest() {
        let conn = test_db();
        insert_test_project(&conn, "p1", "testproj");
        let now = chrono::Utc::now().to_rfc3339();
        conn.execute(
            "INSERT INTO quest_chains (id, goal, project_id, status, created_at) VALUES ('c1', 'test goal', 'p1', 'active', ?1)",
            [&now],
        ).unwrap();
        conn.execute(
            "INSERT INTO quests (id, chain_id, title, description, tier, type, status, project_id, branch, created_at) VALUES ('q1', 'c1', 'Test Quest', 'desc', 'normal', 'implement', 'backlog', 'p1', 'feature/test', ?1)",
            [&now],
        ).unwrap();

        let quest = get_quest(&conn, "q1").unwrap();
        assert!(quest.is_some());
        let (id, title, status, qtype, tier, assigned) = quest.unwrap();
        assert_eq!(id, "q1");
        assert_eq!(title, "Test Quest");
        assert_eq!(status, "backlog");
        assert_eq!(qtype, "implement");
        assert_eq!(tier, "normal");
        assert!(assigned.is_none());

        let missing = get_quest(&conn, "nonexistent").unwrap();
        assert!(missing.is_none());
    }

    #[test]
    fn test_update_quest_status() {
        let conn = test_db();
        insert_test_project(&conn, "p1", "testproj");
        let now = chrono::Utc::now().to_rfc3339();
        conn.execute(
            "INSERT INTO quest_chains (id, goal, project_id, status, created_at) VALUES ('c1', 'test goal', 'p1', 'active', ?1)",
            [&now],
        ).unwrap();
        conn.execute(
            "INSERT INTO quests (id, chain_id, title, description, tier, type, status, project_id, branch, created_at) VALUES ('q1', 'c1', 'Test Quest', 'desc', 'normal', 'implement', 'backlog', 'p1', 'feature/test', ?1)",
            [&now],
        ).unwrap();

        update_quest_status(&conn, "q1", "in_progress").unwrap();
        let quest = get_quest(&conn, "q1").unwrap().unwrap();
        assert_eq!(quest.2, "in_progress");

        update_quest_status(&conn, "q1", "done").unwrap();
        let quest = get_quest(&conn, "q1").unwrap().unwrap();
        assert_eq!(quest.2, "done");

        let completed: Option<String> = conn.query_row(
            "SELECT completed_at FROM quests WHERE id = 'q1'", [], |r| r.get(0)
        ).unwrap();
        assert!(completed.is_some());
    }

    #[test]
    fn test_list_quests_by_status() {
        let conn = test_db();
        insert_test_project(&conn, "p1", "testproj");
        let now = chrono::Utc::now().to_rfc3339();
        conn.execute(
            "INSERT INTO quest_chains (id, goal, project_id, status, created_at) VALUES ('c1', 'test goal', 'p1', 'active', ?1)",
            [&now],
        ).unwrap();
        conn.execute(
            "INSERT INTO quests (id, chain_id, title, description, tier, type, status, project_id, branch, created_at) VALUES ('q1', 'c1', 'Quest A', 'desc', 'normal', 'implement', 'backlog', 'p1', 'feature/a', ?1)",
            [&now],
        ).unwrap();
        conn.execute(
            "INSERT INTO quests (id, chain_id, title, description, tier, type, status, project_id, branch, created_at) VALUES ('q2', 'c1', 'Quest B', 'desc', 'epic', 'implement', 'in_progress', 'p1', 'feature/b', ?1)",
            [&now],
        ).unwrap();

        let backlog = list_quests_by_status(&conn, "backlog").unwrap();
        assert_eq!(backlog.len(), 1);
        assert_eq!(backlog[0].1, "Quest A");

        let in_progress = list_quests_by_status(&conn, "in_progress").unwrap();
        assert_eq!(in_progress.len(), 1);
        assert_eq!(in_progress[0].1, "Quest B");
    }

    #[test]
    fn test_get_project_by_name() {
        let conn = test_db();
        insert_test_project(&conn, "p1", "myproject");

        let proj = get_project_by_name(&conn, "myproject").unwrap();
        assert!(proj.is_some());
        let (id, name, path, provider, main_b, dev_b) = proj.unwrap();
        assert_eq!(id, "p1");
        assert_eq!(name, "myproject");
        assert_eq!(path, "/tmp/test");
        assert_eq!(provider, "none");
        assert_eq!(main_b, "main");
        assert_eq!(dev_b, "development");

        let missing = get_project_by_name(&conn, "nope").unwrap();
        assert!(missing.is_none());
    }

    #[test]
    fn test_update_project_status() {
        let conn = test_db();
        insert_test_project(&conn, "p1", "myproject");

        update_project_status(&conn, "myproject", "paused").unwrap();

        let status: String = conn.query_row(
            "SELECT status FROM projects WHERE name = 'myproject'", [], |r| r.get(0)
        ).unwrap();
        assert_eq!(status, "paused");
    }

    #[test]
    fn test_get_recent_activity() {
        let conn = test_db();
        log_activity(&conn, "hero1", "started quest", None, None, "info").unwrap();
        log_activity(&conn, "hero2", "completed quest", None, None, "info").unwrap();
        log_activity(&conn, "system", "warning", None, None, "warn").unwrap();

        let recent = get_recent_activity(&conn, 2).unwrap();
        assert_eq!(recent.len(), 2);
        assert_eq!(recent[0].1, "system");
        assert_eq!(recent[1].1, "hero2");

        let all = get_recent_activity(&conn, 10).unwrap();
        assert_eq!(all.len(), 3);
    }
}
