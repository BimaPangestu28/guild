use anyhow::{bail, Result};
use colored::Colorize;
use std::fs;

use crate::db;

pub fn run(project: Option<String>) -> Result<()> {
    let guild_dir = db::guild_dir();

    if guild_dir.join("guild.db").exists() {
        bail!("Guild already initialized at {}", guild_dir.display());
    }

    println!("{}", "[1/4] Creating guild workspace...".yellow());

    // Create directory structure
    let dirs = [
        "workspace/memory/shared/projects",
        "workspace/memory/shared/conventions",
        "workspace/memory/heroes",
        "workspace/quests/backlog",
        "workspace/quests/active",
        "workspace/quests/done",
        "workspace/projects",
        "workspace/inbox",
        "workspace/outbox",
        "workspace/heroes",
        "backups",
    ];

    for dir in &dirs {
        fs::create_dir_all(guild_dir.join(dir))?;
    }

    println!("  {} Directory structure created", "✓".green());

    // Initialize database
    println!("{}", "[2/4] Initializing database...".yellow());
    let db_path = guild_dir.join("guild.db");
    let conn = db::init_at(&db_path)?;
    println!("  {} SQLite database initialized", "✓".green());

    // Write default convention templates
    println!("{}", "[3/4] Writing default templates...".yellow());
    write_default_conventions(&guild_dir)?;
    println!("  {} Default conventions written", "✓".green());

    // Log initialization
    db::log_activity(&conn, "system", "Guild initialized", None, None, "info")?;

    println!("{}", "[4/4] Done!".yellow());
    println!();
    println!("{}", "Guild initialized successfully.".green().bold());
    println!("  Location: {}", guild_dir.display());
    println!();
    println!("Next steps:");
    println!("  {} — register a project", "guild project add".cyan());
    println!("  {} — recruit your first hero", "guild recruit".cyan());
    println!("  {} — set your first goal", "guild goal \"...\"".cyan());

    if let Some(path) = project {
        println!();
        println!("Registering project: {}", path);
        // TODO: call project::add with the path
    }

    Ok(())
}

fn write_default_conventions(guild_dir: &std::path::Path) -> Result<()> {
    let conv_dir = guild_dir.join("workspace/memory/shared/conventions");

    fs::write(
        conv_dir.join("git.md"),
        "# Git Conventions\n\n\
         ## Branch Naming\n\
         - `feature/GLD-{id}-{slug}` — new features\n\
         - `fix/GLD-{id}-{slug}` — bug fixes\n\
         - `chore/GLD-{id}-{slug}` — maintenance\n\n\
         ## Commit Format\n\
         ```\n\
         [GLD-{id}] {short description} — {hero_name}\n\
         ```\n\n\
         ## Rules\n\
         - Branches always from `development`, never from `main`\n\
         - PRs always target `development`\n\
         - `development` → `main` requires human approval\n\
         - Never force push\n",
    )?;

    fs::write(
        conv_dir.join("code-style.md"),
        "# Code Style\n\n\
         Detected conventions will be added here when projects are registered.\n",
    )?;

    fs::write(
        conv_dir.join("testing.md"),
        "# Testing Standards\n\n\
         Testing conventions will be added here as projects are registered.\n",
    )?;

    Ok(())
}
