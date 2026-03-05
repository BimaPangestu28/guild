use anyhow::Result;
use colored::Colorize;

use crate::db;

pub fn run_status() -> Result<()> {
    let conn = db::open()?;

    // Heroes
    let hero_count: i32 = conn.query_row("SELECT COUNT(*) FROM heroes", [], |r| r.get(0))?;
    let online: i32 = conn.query_row(
        "SELECT COUNT(*) FROM heroes WHERE status != 'offline'", [], |r| r.get(0)
    )?;
    let on_quest: i32 = conn.query_row(
        "SELECT COUNT(*) FROM heroes WHERE status = 'on_quest'", [], |r| r.get(0)
    )?;

    // Quests
    let active: i32 = conn.query_row(
        "SELECT COUNT(*) FROM quests WHERE status = 'active'", [], |r| r.get(0)
    )?;
    let backlog: i32 = conn.query_row(
        "SELECT COUNT(*) FROM quests WHERE status = 'backlog'", [], |r| r.get(0)
    )?;
    let blocked: i32 = conn.query_row(
        "SELECT COUNT(*) FROM quests WHERE status = 'blocked'", [], |r| r.get(0)
    )?;
    let done_today: i32 = conn.query_row(
        "SELECT COUNT(*) FROM quests WHERE status = 'done' AND completed_at >= date('now')",
        [], |r| r.get(0)
    )?;

    // Projects
    let project_count: i32 = conn.query_row(
        "SELECT COUNT(*) FROM projects WHERE status = 'active'", [], |r| r.get(0)
    )?;

    println!("{}", "═══ GUILD STATUS ═══".yellow().bold());
    println!();

    println!("{}", "HEROES".yellow());
    println!("  Online: {}/{} | On quest: {}", online, hero_count, on_quest);
    println!();

    println!("{}", "QUESTS".yellow());
    println!(
        "  Active: {} | Backlog: {} | Blocked: {} | Done today: {}",
        active.to_string().blue(),
        backlog,
        if blocked > 0 { blocked.to_string().red().to_string() } else { "0".into() },
        done_today.to_string().green(),
    );
    println!();

    println!("{}", "PROJECTS".yellow());
    println!("  Active: {}", project_count);

    Ok(())
}

pub fn run_log(count: usize) -> Result<()> {
    let conn = db::open()?;
    let mut stmt = conn.prepare(
        "SELECT timestamp, actor, action, quest_id, level FROM activity_log ORDER BY timestamp DESC LIMIT ?1"
    )?;
    let rows = stmt.query_map([count], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, Option<String>>(3)?,
            row.get::<_, String>(4)?,
        ))
    })?;

    println!("{}", "ACTIVITY LOG".yellow().bold());
    println!("{}", "─".repeat(70));

    for row in rows {
        let (ts, actor, action, quest_id, level) = row?;
        let time = &ts[11..16]; // HH:MM
        let action_colored = match level.as_str() {
            "warning" => action.yellow(),
            "critical" => action.red(),
            _ => action.normal(),
        };
        print!("  {} {} {}", time.dimmed(), actor.cyan(), action_colored);
        if let Some(q) = quest_id {
            print!(" [{}]", q.dimmed());
        }
        println!();
    }

    Ok(())
}

pub fn run_report() -> Result<()> {
    let guild_dir = db::guild_dir();
    let report_path = guild_dir.join("workspace/outbox/guild-master.md");

    match std::fs::read_to_string(&report_path) {
        Ok(content) if !content.is_empty() => {
            println!("{}", "GUILD MASTER REPORT".yellow().bold());
            println!("{}", "─".repeat(40));
            println!("{}", content);
        }
        _ => {
            println!("{}", "No Guild Master report available yet.".dimmed());
        }
    }

    Ok(())
}

pub fn run_cost() -> Result<()> {
    println!("{}", "COST TRACKING".yellow().bold());
    println!("{}", "Cost tracking will be available with Claude Code SDK integration.".dimmed());
    Ok(())
}
