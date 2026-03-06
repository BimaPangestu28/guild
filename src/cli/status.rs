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
    let conn = db::open()?;

    let (total_cost, total_input, total_output) = db::get_cost_today(&conn)?;
    let cap = db::get_cost_daily_cap(&conn);
    let today = chrono::Utc::now().format("%Y-%m-%d").to_string();
    let by_actor = db::get_cost_by_actor(&conn, &today)?;
    let by_project = db::get_cost_by_project(&conn, &today)?;

    println!("{}", "COST TRACKING".yellow().bold());
    println!("{}", "─".repeat(50));

    let pct = if cap > 0.0 { (total_cost / cap) * 100.0 } else { 0.0 };
    let cost_str = format!("${:.2} / ${:.2} ({:.0}%)", total_cost, cap, pct);
    let cost_colored = if pct > 80.0 {
        cost_str.red()
    } else if pct > 60.0 {
        cost_str.yellow()
    } else {
        cost_str.green()
    };
    println!("  Today: {}", cost_colored);

    // Progress bar
    let bar_width = 30;
    let filled = ((pct / 100.0) * bar_width as f64).min(bar_width as f64) as usize;
    let empty = bar_width - filled;
    let bar = format!("[{}{}]", "#".repeat(filled), "-".repeat(empty));
    let bar_colored = if pct > 80.0 {
        bar.red()
    } else if pct > 60.0 {
        bar.yellow()
    } else {
        bar.green()
    };
    println!("  {}", bar_colored);

    println!(
        "  Tokens: {} input / {} output",
        format_tokens(total_input),
        format_tokens(total_output),
    );
    println!();

    if !by_actor.is_empty() {
        println!("  {}", "BY ACTOR".yellow());
        for (actor, cost) in &by_actor {
            println!("    {:<20} ${:.4}", actor.cyan(), cost);
        }
        println!();
    }

    if !by_project.is_empty() {
        println!("  {}", "BY PROJECT".yellow());
        for (project, cost) in &by_project {
            println!("    {:<20} ${:.4}", project.cyan(), cost);
        }
        println!();
    }

    if by_actor.is_empty() && by_project.is_empty() {
        println!("  {}", "No cost data recorded today.".dimmed());
    }

    Ok(())
}

fn format_tokens(tokens: i64) -> String {
    if tokens >= 1_000_000 {
        format!("{:.1}M", tokens as f64 / 1_000_000.0)
    } else if tokens >= 1_000 {
        format!("{:.1}K", tokens as f64 / 1_000.0)
    } else {
        tokens.to_string()
    }
}
