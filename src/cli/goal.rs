use anyhow::Result;
use colored::Colorize;

use crate::db;

pub fn run(description: String, project: Option<String>) -> Result<()> {
    let conn = db::open()?;

    // Write goal to Guild Master inbox
    let guild_dir = db::guild_dir();
    let inbox_path = guild_dir.join("workspace/inbox/guild-master.md");

    let goal_entry = format!(
        "## Goal\n{}\n{}\n\n",
        description,
        project
            .as_ref()
            .map(|p| format!("Project: {}", p))
            .unwrap_or_default(),
    );

    // Append to inbox
    let existing = std::fs::read_to_string(&inbox_path).unwrap_or_default();
    std::fs::write(&inbox_path, format!("{}{}", existing, goal_entry))?;

    db::log_activity(
        &conn,
        "developer",
        &format!("Goal posted: {}", description),
        None,
        project.as_deref(),
        "info",
    )?;

    println!("{} Goal posted to Guild Master", "✓".green());
    println!("  \"{}\"", description.italic());
    if let Some(p) = &project {
        println!("  Project: {}", p);
    }
    println!();
    println!(
        "{}",
        "Guild Master will decompose this into quests."
            .dimmed()
    );

    let gm_pid_file = guild_dir.join("guild-master.pid");
    if gm_pid_file.exists() {
        println!(
            "  {} Guild Master will pick this up on next cycle",
            "→".dimmed()
        );
    } else {
        println!(
            "  {} Guild Master is not running. Start with: python3 agents/guild_master.py",
            "!".yellow()
        );
    }

    Ok(())
}
