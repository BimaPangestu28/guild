use anyhow::{bail, Result};
use chrono::Utc;
use clap::Subcommand;
use colored::Colorize;

use crate::db;

#[derive(Subcommand)]
pub enum McpCommand {
    /// Add a new MCP server
    Add {
        #[arg(long)]
        name: String,
        /// Display name
        #[arg(long)]
        display: Option<String>,
        /// URL for remote MCP
        #[arg(long)]
        url: Option<String>,
        /// Command for local MCP
        #[arg(long)]
        command: Option<String>,
        /// Args for local MCP
        #[arg(long)]
        args: Option<String>,
        /// Skills this MCP provides (comma-separated)
        #[arg(long)]
        skills: Option<String>,
    },
    /// Remove an MCP server
    Remove { name: String },
    /// List all MCP servers
    List,
    /// Show MCP status (which heroes have which MCPs)
    Status,
    /// Attach MCP to a hero or project
    Attach {
        /// Hero name (omit if using --project)
        #[arg(required_unless_present = "project")]
        hero: Option<String>,
        /// MCP name
        mcp: String,
        /// Auto-attach on every session (hero-level only)
        #[arg(long)]
        auto: bool,
        /// Attach as project default instead of hero-level
        #[arg(long)]
        project: Option<String>,
    },
    /// Detach MCP from a hero or project
    Detach {
        /// Hero name (omit if using --project)
        #[arg(required_unless_present = "project")]
        hero: Option<String>,
        /// MCP name
        mcp: String,
        /// Detach from project defaults instead of hero-level
        #[arg(long)]
        project: Option<String>,
    },
}

pub fn run(cmd: McpCommand) -> Result<()> {
    match cmd {
        McpCommand::Add { name, display, url, command, args, skills } => {
            run_add(name, display, url, command, args, skills)
        }
        McpCommand::Remove { name } => run_remove(name),
        McpCommand::List => run_list(),
        McpCommand::Status => run_status(),
        McpCommand::Attach { hero, mcp, auto, project } => {
            if let Some(project_name) = project {
                run_attach_project(&project_name, &mcp)
            } else {
                run_attach(hero.unwrap(), mcp, auto)
            }
        }
        McpCommand::Detach { hero, mcp, project } => {
            if let Some(project_name) = project {
                run_detach_project(&project_name, &mcp)
            } else {
                run_detach(hero.unwrap(), mcp)
            }
        }
    }
}

fn resolve_hero(conn: &rusqlite::Connection, name: &str) -> Result<(String, String)> {
    conn.query_row(
        "SELECT id, name FROM heroes WHERE name = ?1",
        [name],
        |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
    )
    .map_err(|_| anyhow::anyhow!("Hero '{}' not found", name))
}

fn resolve_mcp(conn: &rusqlite::Connection, name: &str) -> Result<(String, String)> {
    conn.query_row(
        "SELECT id, name FROM mcp_servers WHERE name = ?1",
        [name],
        |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
    )
    .map_err(|_| anyhow::anyhow!("MCP server '{}' not found", name))
}

fn run_add(
    name: String,
    display: Option<String>,
    url: Option<String>,
    command: Option<String>,
    args: Option<String>,
    skills: Option<String>,
) -> Result<()> {
    if url.is_none() && command.is_none() {
        bail!("Either --url or --command must be provided");
    }

    let conn = db::open()?;

    // Check if name already exists
    let exists: bool = conn
        .query_row(
            "SELECT COUNT(*) FROM mcp_servers WHERE name = ?1",
            [&name],
            |row| row.get::<_, i32>(0),
        )
        .map(|c| c > 0)
        .unwrap_or(false);

    if exists {
        bail!("MCP server '{}' already exists", name);
    }

    let id = uuid::Uuid::new_v4().to_string();
    let now = Utc::now().to_rfc3339();
    let display_name = display.unwrap_or_else(|| name.clone());
    let skills_json = skills
        .map(|s| {
            let list: Vec<String> = s.split(',').map(|sk| sk.trim().to_string()).collect();
            serde_json::to_string(&list).unwrap_or_else(|_| "[]".to_string())
        })
        .unwrap_or_else(|| "[]".to_string());

    conn.execute(
        "INSERT INTO mcp_servers (id, name, display_name, url, command, args, skills_served, status, added_at) \
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 'active', ?8)",
        rusqlite::params![id, name, display_name, url, command, args, skills_json, now],
    )?;

    db::log_activity(
        &conn,
        "system",
        &format!("MCP server '{}' added", name),
        None,
        None,
        "info",
    )?;

    let mcp_type = if url.is_some() { "url (remote)" } else { "command (local)" };
    println!(
        "{} MCP server '{}' added ({})",
        "✓".green(),
        name.bold(),
        mcp_type.dimmed()
    );

    Ok(())
}

fn run_remove(name: String) -> Result<()> {
    let conn = db::open()?;
    let (mcp_id, mcp_name) = resolve_mcp(&conn, &name)?;

    // Remove hero attachments first
    conn.execute("DELETE FROM hero_mcps WHERE mcp_id = ?1", [&mcp_id])?;

    let deleted = conn.execute("DELETE FROM mcp_servers WHERE id = ?1", [&mcp_id])?;
    if deleted == 0 {
        bail!("MCP server '{}' not found", name);
    }

    db::log_activity(
        &conn,
        "system",
        &format!("MCP server '{}' removed", mcp_name),
        None,
        None,
        "info",
    )?;

    println!("{} MCP server '{}' removed", "✓".green(), mcp_name.bold());

    Ok(())
}

fn run_list() -> Result<()> {
    let conn = db::open()?;

    let mut stmt = conn.prepare(
        "SELECT name, display_name, url, command, skills_served, status FROM mcp_servers ORDER BY name"
    )?;
    let servers = stmt.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, Option<String>>(2)?,
            row.get::<_, Option<String>>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, String>(5)?,
        ))
    })?;

    println!("{}", "MCP SERVERS".yellow().bold());
    println!("{}", "─".repeat(70));

    let mut count = 0;
    for server in servers {
        let (name, display_name, url, command, skills_served, status) = server?;
        let mcp_type = if url.is_some() { "url" } else { "command" };

        let status_colored = match status.as_str() {
            "active" => status.green(),
            "inactive" => status.red(),
            _ => status.dimmed(),
        };

        println!(
            "  {} ({}) [{}] — {}",
            name.bold(),
            display_name,
            mcp_type.cyan(),
            status_colored,
        );

        // Parse and display skills
        if let Ok(skills) = serde_json::from_str::<Vec<String>>(&skills_served) {
            if !skills.is_empty() {
                println!(
                    "    Skills: {}",
                    skills.join(", ").dimmed()
                );
            }
        }

        // Show connection info
        if let Some(ref u) = url {
            println!("    URL: {}", u.dimmed());
        }
        if let Some(ref c) = command {
            println!("    Command: {}", c.dimmed());
        }

        count += 1;
    }

    if count == 0 {
        println!("  No MCP servers registered. Use {} to add one.", "guild mcp add".cyan());
    } else {
        println!("\n  {} server(s) registered.", count);
    }

    Ok(())
}

fn run_status() -> Result<()> {
    let conn = db::open()?;

    let mut stmt = conn.prepare(
        "SELECT h.name AS hero_name, h.status AS hero_status, \
                m.name AS mcp_name, m.display_name, hm.auto_attach \
         FROM hero_mcps hm \
         JOIN heroes h ON hm.hero_id = h.id \
         JOIN mcp_servers m ON hm.mcp_id = m.id \
         ORDER BY h.name, m.name"
    )?;

    let rows = stmt.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, bool>(4)?,
        ))
    })?;

    println!("{}", "MCP STATUS".yellow().bold());
    println!("{}", "─".repeat(70));

    let mut current_hero = String::new();
    let mut has_rows = false;

    for row in rows {
        let (hero_name, hero_status, mcp_name, display_name, auto_attach) = row?;
        has_rows = true;

        if hero_name != current_hero {
            if !current_hero.is_empty() {
                println!();
            }
            let status_colored = match hero_status.as_str() {
                "idle" => hero_status.green(),
                "on_quest" => hero_status.yellow(),
                "offline" => hero_status.dimmed(),
                _ => hero_status.normal(),
            };
            println!("  {} ({})", hero_name.cyan().bold(), status_colored);
            current_hero = hero_name;
        }

        let auto_tag = if auto_attach { " [auto]".green() } else { "".normal() };
        println!(
            "    {} ({}){}", mcp_name.bold(), display_name.dimmed(), auto_tag
        );
    }

    if !has_rows {
        // Show heroes without MCPs
        let mut hero_stmt = conn.prepare("SELECT name, status FROM heroes ORDER BY name")?;
        let heroes = hero_stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?;

        let mut any_hero = false;
        for hero in heroes {
            let (name, status) = hero?;
            any_hero = true;
            let status_colored = match status.as_str() {
                "idle" => status.green(),
                "on_quest" => status.yellow(),
                "offline" => status.dimmed(),
                _ => status.normal(),
            };
            println!("  {} ({}) — no MCPs attached", name.cyan().bold(), status_colored);
        }

        if !any_hero {
            println!("  No heroes recruited. Use {} first.", "guild recruit".cyan());
        }
    }

    Ok(())
}

fn run_attach(hero: String, mcp: String, auto: bool) -> Result<()> {
    let conn = db::open()?;
    let (hero_id, hero_name) = resolve_hero(&conn, &hero)?;
    let (mcp_id, mcp_name) = resolve_mcp(&conn, &mcp)?;

    // Check if already attached
    let exists: bool = conn
        .query_row(
            "SELECT COUNT(*) FROM hero_mcps WHERE hero_id = ?1 AND mcp_id = ?2",
            rusqlite::params![hero_id, mcp_id],
            |row| row.get::<_, i32>(0),
        )
        .map(|c| c > 0)
        .unwrap_or(false);

    if exists {
        // Update auto_attach if needed
        conn.execute(
            "UPDATE hero_mcps SET auto_attach = ?1 WHERE hero_id = ?2 AND mcp_id = ?3",
            rusqlite::params![auto as i32, hero_id, mcp_id],
        )?;
        println!(
            "{} MCP '{}' already attached to hero '{}' (auto_attach updated to {})",
            "✓".green(),
            mcp_name.bold(),
            hero_name.cyan(),
            auto
        );
        return Ok(());
    }

    let now = Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO hero_mcps (hero_id, mcp_id, auto_attach, added_at) VALUES (?1, ?2, ?3, ?4)",
        rusqlite::params![hero_id, mcp_id, auto as i32, now],
    )?;

    db::log_activity(
        &conn,
        "system",
        &format!("MCP '{}' attached to hero '{}'", mcp_name, hero_name),
        None,
        None,
        "info",
    )?;

    let auto_tag = if auto { " (auto-attach)" } else { "" };
    println!(
        "{} MCP '{}' attached to hero '{}'{}",
        "✓".green(),
        mcp_name.bold(),
        hero_name.cyan(),
        auto_tag.green()
    );

    Ok(())
}

fn run_detach(hero: String, mcp: String) -> Result<()> {
    let conn = db::open()?;
    let (hero_id, hero_name) = resolve_hero(&conn, &hero)?;
    let (mcp_id, mcp_name) = resolve_mcp(&conn, &mcp)?;

    let deleted = conn.execute(
        "DELETE FROM hero_mcps WHERE hero_id = ?1 AND mcp_id = ?2",
        rusqlite::params![hero_id, mcp_id],
    )?;

    if deleted == 0 {
        bail!(
            "MCP '{}' is not attached to hero '{}'",
            mcp_name,
            hero_name
        );
    }

    db::log_activity(
        &conn,
        "system",
        &format!("MCP '{}' detached from hero '{}'", mcp_name, hero_name),
        None,
        None,
        "info",
    )?;

    println!(
        "{} MCP '{}' detached from hero '{}'",
        "✓".green(),
        mcp_name.bold(),
        hero_name.cyan()
    );

    Ok(())
}

fn run_attach_project(project_name: &str, mcp_name: &str) -> Result<()> {
    let conn = db::open()?;

    let mcp_exists: bool = conn
        .query_row(
            "SELECT COUNT(*) FROM mcp_servers WHERE name = ?1",
            [mcp_name],
            |row| row.get::<_, i64>(0),
        )
        .map(|c| c > 0)
        .unwrap_or(false);

    if !mcp_exists {
        bail!(
            "MCP '{}' not found. Use `guild mcp list` to see available MCPs.",
            mcp_name
        );
    }

    let current: String = conn
        .query_row(
            "SELECT COALESCE(default_mcps, '') FROM projects WHERE name = ?1",
            [project_name],
            |row| row.get(0),
        )
        .map_err(|_| anyhow::anyhow!("Project '{}' not found", project_name))?;

    let mut mcps: Vec<String> = if current.is_empty() {
        vec![]
    } else {
        current.split(',').map(|s| s.trim().to_string()).collect()
    };

    if !mcps.contains(&mcp_name.to_string()) {
        mcps.push(mcp_name.to_string());
    }

    conn.execute(
        "UPDATE projects SET default_mcps = ?1 WHERE name = ?2",
        rusqlite::params![mcps.join(","), project_name],
    )?;

    db::log_activity(
        &conn,
        "system",
        &format!("MCP '{}' attached to project '{}'", mcp_name, project_name),
        None,
        None,
        "info",
    )?;

    println!(
        "{} MCP '{}' attached to project '{}'",
        "✓".green(),
        mcp_name.cyan(),
        project_name.bold()
    );
    Ok(())
}

fn run_detach_project(project_name: &str, mcp_name: &str) -> Result<()> {
    let conn = db::open()?;

    let current: String = conn
        .query_row(
            "SELECT COALESCE(default_mcps, '') FROM projects WHERE name = ?1",
            [project_name],
            |row| row.get(0),
        )
        .map_err(|_| anyhow::anyhow!("Project '{}' not found", project_name))?;

    let mcps: Vec<String> = current
        .split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty() && s != mcp_name)
        .collect();

    conn.execute(
        "UPDATE projects SET default_mcps = ?1 WHERE name = ?2",
        rusqlite::params![mcps.join(","), project_name],
    )?;

    db::log_activity(
        &conn,
        "system",
        &format!("MCP '{}' detached from project '{}'", mcp_name, project_name),
        None,
        None,
        "info",
    )?;

    println!(
        "{} MCP '{}' detached from project '{}'",
        "✓".green(),
        mcp_name.cyan(),
        project_name.bold()
    );
    Ok(())
}
