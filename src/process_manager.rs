use anyhow::{bail, Result};
use std::process::Command;
use crate::db;

/// Start a hero session by spawning the Python hero_runtime
pub fn start_session(hero_name: &str) -> Result<u32> {
    let conn = db::open()?;

    // Get hero info
    let (hero_id, current_quest): (String, Option<String>) = conn.query_row(
        "SELECT id, current_quest_id FROM heroes WHERE name = ?1",
        [hero_name],
        |row| Ok((row.get(0)?, row.get(1)?)),
    ).map_err(|_| anyhow::anyhow!("Hero '{}' not found", hero_name))?;

    // Get project path from quest
    let project_path: Option<String> = if let Some(ref qid) = current_quest {
        conn.query_row(
            "SELECT p.path FROM projects p JOIN quests q ON q.project_id = p.id OR q.project_id = p.name WHERE q.id = ?1",
            [qid.as_str()],
            |row| row.get(0),
        ).ok()
    } else {
        None
    };

    let guild_dir = db::guild_dir();
    let _claude_md = guild_dir.join("workspace/memory/heroes").join(hero_name).join("CLAUDE.md");

    // Find the agents directory relative to the binary or use env
    let agents_dir = std::env::var("GUILD_AGENTS_DIR")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| {
            // Try relative to cwd
            let cwd = std::env::current_dir().unwrap_or_default();
            cwd.join("agents")
        });

    let mut cmd = Command::new("python3");
    cmd.arg(agents_dir.join("hero_runtime.py"))
        .arg("--hero")
        .arg(hero_name);

    if let Some(ref path) = project_path {
        cmd.current_dir(path);
    }

    let child = cmd.spawn()?;
    let pid = child.id();

    // Store PID in DB
    conn.execute(
        "UPDATE heroes SET session_pid = ?1, status = 'on_quest' WHERE id = ?2",
        rusqlite::params![pid as i64, hero_id],
    )?;

    db::log_activity(&conn, hero_name, &format!("Session started (PID: {})", pid), current_quest.as_deref(), None, "info")?;

    Ok(pid)
}

/// Stop a hero session by PID
pub fn stop_session(hero_name: &str) -> Result<()> {
    let conn = db::open()?;

    let (hero_id, pid): (String, Option<i64>) = conn.query_row(
        "SELECT id, session_pid FROM heroes WHERE name = ?1",
        [hero_name],
        |row| Ok((row.get(0)?, row.get(1)?)),
    ).map_err(|_| anyhow::anyhow!("Hero '{}' not found", hero_name))?;

    if let Some(pid) = pid {
        // Send SIGTERM
        #[cfg(unix)]
        unsafe {
            libc::kill(pid as i32, libc::SIGTERM);
        }

        conn.execute(
            "UPDATE heroes SET session_pid = NULL, status = 'idle' WHERE id = ?1",
            [&hero_id],
        )?;

        db::log_activity(&conn, hero_name, &format!("Session stopped (PID: {})", pid), None, None, "info")?;
    } else {
        bail!("Hero '{}' has no active session", hero_name);
    }

    Ok(())
}

/// Check if a session is alive
pub fn is_session_alive(pid: u32) -> bool {
    #[cfg(unix)]
    unsafe {
        libc::kill(pid as i32, 0) == 0
    }
    #[cfg(not(unix))]
    {
        let _ = pid;
        false
    }
}

/// Run heartbeat check on all heroes with active sessions
pub fn heartbeat() -> Result<Vec<String>> {
    let conn = db::open()?;
    let mut problems = vec![];

    let mut stmt = conn.prepare(
        "SELECT id, name, session_pid, current_quest_id FROM heroes WHERE session_pid IS NOT NULL"
    )?;
    let rows = stmt.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, i64>(2)?,
            row.get::<_, Option<String>>(3)?,
        ))
    })?;

    for row in rows {
        let (hero_id, name, pid, quest_id) = row?;
        if !is_session_alive(pid as u32) {
            // Dead PID detected
            conn.execute(
                "UPDATE heroes SET session_pid = NULL, status = 'offline' WHERE id = ?1",
                [&hero_id],
            )?;

            if let Some(qid) = &quest_id {
                // Reset quest to backlog
                conn.execute(
                    "UPDATE quests SET status = 'backlog', assigned_to = NULL WHERE id = ?1",
                    [qid.as_str()],
                )?;
                conn.execute(
                    "UPDATE heroes SET current_quest_id = NULL WHERE id = ?1",
                    [&hero_id],
                )?;
                problems.push(format!("{}: session died (PID {}), quest {} reset to backlog", name, pid, qid));
            } else {
                problems.push(format!("{}: session died (PID {})", name, pid));
            }

            db::log_activity(&conn, &name, &format!("Session crashed (PID: {})", pid), quest_id.as_deref(), None, "warning")?;
        }
    }

    Ok(problems)
}
