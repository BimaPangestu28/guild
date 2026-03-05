use anyhow::{bail, Result};
use colored::Colorize;

use crate::db;

use clap::Subcommand;

#[derive(Subcommand)]
pub enum QuestCommand {
    /// Show quest detail
    Show { id: String },
    /// Add a quest manually
    Add,
    /// Cancel a quest
    Cancel { id: String },
    /// Mark a quest done manually
    Complete { id: String },
}

pub fn run(cmd: QuestCommand) -> Result<()> {
    match cmd {
        QuestCommand::Show { id } => run_show(&id),
        QuestCommand::Add => run_add(),
        QuestCommand::Cancel { id } => run_set_status(&id, "cancelled"),
        QuestCommand::Complete { id } => run_set_status(&id, "done"),
    }
}

pub fn run_list(project: Option<String>, status: Option<String>) -> Result<()> {
    let conn = db::open()?;

    let mut sql = String::from(
        "SELECT q.id, q.title, q.tier, q.type, q.status, q.project_id, h.name \
         FROM quests q LEFT JOIN heroes h ON q.assigned_to = h.id WHERE 1=1"
    );
    let mut params: Vec<Box<dyn rusqlite::types::ToSql>> = vec![];

    if let Some(ref p) = project {
        sql.push_str(" AND q.project_id = ?");
        params.push(Box::new(p.clone()));
    }
    if let Some(ref s) = status {
        sql.push_str(" AND q.status = ?");
        params.push(Box::new(s.clone()));
    }
    sql.push_str(" ORDER BY q.created_at DESC");

    let mut stmt = conn.prepare(&sql)?;
    let param_refs: Vec<&dyn rusqlite::types::ToSql> = params.iter().map(|p| p.as_ref()).collect();
    let rows = stmt.query_map(param_refs.as_slice(), |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, String>(5)?,
            row.get::<_, Option<String>>(6)?,
        ))
    })?;

    println!("{}", "QUEST BOARD".yellow().bold());
    println!("{}", "─".repeat(70));

    let mut count = 0;
    for row in rows {
        let (id, title, tier, qtype, status, project_id, hero) = row?;
        let tier_colored = match tier.as_str() {
            "COMMON" => tier.dimmed(),
            "RARE" => tier.blue(),
            "EPIC" => tier.purple(),
            "LEGENDARY" => tier.yellow(),
            "BOSS" => tier.red(),
            _ => tier.normal(),
        };
        let status_colored = match status.as_str() {
            "active" => status.blue(),
            "backlog" => status.dimmed(),
            "blocked" => status.red(),
            "done" => status.green(),
            _ => status.normal(),
        };
        print!(
            "  {} [{}] [{}] {} — {}",
            id.cyan(),
            tier_colored,
            qtype,
            title,
            status_colored,
        );
        if let Some(h) = hero {
            print!(" → {}", h.yellow());
        }
        println!(" ({})", project_id.dimmed());
        count += 1;
    }

    if count == 0 {
        println!("  No quests found.");
    }

    Ok(())
}

pub fn run_assign(quest_id: String, hero_name: String) -> Result<()> {
    let conn = db::open()?;

    let hero_id: String = conn.query_row(
        "SELECT id FROM heroes WHERE name = ?1",
        [&hero_name],
        |r| r.get(0),
    ).map_err(|_| anyhow::anyhow!("Hero '{}' not found", hero_name))?;

    let updated = conn.execute(
        "UPDATE quests SET assigned_to = ?1, status = 'active' WHERE id = ?2",
        rusqlite::params![hero_id, quest_id],
    )?;

    if updated == 0 {
        bail!("Quest '{}' not found", quest_id);
    }

    conn.execute(
        "UPDATE heroes SET status = 'on_quest', current_quest_id = ?1 WHERE id = ?2",
        rusqlite::params![quest_id, hero_id],
    )?;

    println!("{} Quest {} assigned to {}", "✓".green(), quest_id.cyan(), hero_name.yellow());
    Ok(())
}

fn run_show(id: &str) -> Result<()> {
    let conn = db::open()?;

    let row = conn.query_row(
        "SELECT q.id, q.title, q.description, q.tier, q.type, q.status, q.project_id, q.branch, q.chain_id, h.name \
         FROM quests q LEFT JOIN heroes h ON q.assigned_to = h.id WHERE q.id = ?1",
        [id],
        |row| Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, String>(5)?,
            row.get::<_, String>(6)?,
            row.get::<_, String>(7)?,
            row.get::<_, String>(8)?,
            row.get::<_, Option<String>>(9)?,
        ))
    );

    match row {
        Ok((id, title, desc, tier, qtype, status, project, branch, chain, hero)) => {
            println!("{} {} — {}", "Quest:".yellow(), id.cyan().bold(), title);
            println!("  {}", desc);
            println!("  Tier: {} | Type: {} | Status: {}", tier, qtype, status);
            println!("  Project: {} | Chain: {}", project, chain);
            println!("  Branch: {}", branch);
            if let Some(h) = hero {
                println!("  Assigned: {}", h);
            }
        }
        Err(_) => bail!("Quest '{}' not found", id),
    }

    Ok(())
}

fn run_add() -> Result<()> {
    println!("Interactive quest creation — coming soon");
    println!("Quests are typically created by Guild Master from goals.");
    Ok(())
}

fn run_set_status(id: &str, status: &str) -> Result<()> {
    let conn = db::open()?;
    let now = chrono::Utc::now().to_rfc3339();
    let updated = conn.execute(
        "UPDATE quests SET status = ?1, completed_at = ?2 WHERE id = ?3",
        rusqlite::params![status, now, id],
    )?;
    if updated == 0 {
        bail!("Quest '{}' not found", id);
    }

    // Release file locks when quest is done or cancelled
    if status == "done" || status == "cancelled" {
        let released = db::release_locks(&conn, id)?;
        if released > 0 {
            println!("  Released {} file lock(s)", released);
        }
    }

    println!("{} Quest {} → {}", "✓".green(), id.cyan(), status);
    Ok(())
}
