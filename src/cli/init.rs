use anyhow::{bail, Result};
use chrono::Utc;
use colored::Colorize;
use serde_json::Value;
use std::fs;

use crate::db;

pub fn run(project: Option<String>) -> Result<()> {
    let guild_dir = db::guild_dir();
    let first_init = !guild_dir.exists();

    if guild_dir.join("guild.db").exists() {
        bail!("Guild already initialized at {}", guild_dir.display());
    }

    if first_init {
        println!();
        println!("{}", "=== Welcome to Guild ===".green().bold());
        println!();
        println!("Guild is a self-hosted multi-agent development OS.");
        println!("It lets you recruit AI heroes, assign quests, and manage");
        println!("your development workflow from the command line.");
        println!();
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

    // Write onboarding config for first-time init
    if first_init {
        let config_path = guild_dir.join("config.json");
        let mut config: Value = if config_path.exists() {
            let content = fs::read_to_string(&config_path)?;
            serde_json::from_str(&content).unwrap_or(Value::Object(serde_json::Map::new()))
        } else {
            Value::Object(serde_json::Map::new())
        };

        let obj = config.as_object_mut().expect("config must be an object");
        obj.insert("created_at".to_string(), Value::String(Utc::now().to_rfc3339()));
        obj.insert("rookie_mode".to_string(), Value::Bool(true));

        fs::write(&config_path, serde_json::to_string_pretty(&config)?)?;
    }

    println!("{}", "[4/4] Done!".yellow());
    println!();
    println!("{}", "Guild initialized successfully.".green().bold());
    println!("  Location: {}", guild_dir.display());
    println!();

    if first_init {
        let license = crate::license::License::load();
        println!("{}", "Getting Started:".yellow().bold());
        println!("  1. {} — register a project", "guild project add".cyan());
        println!("  2. {} — recruit your first hero", "guild recruit".cyan());
        println!("  3. {} — set your first goal", "guild goal \"...\"".cyan());
        println!("  4. {} — check guild status anytime", "guild status".cyan());
        println!();
        println!(
            "  License: {:?} (max {} heroes). Use {} to upgrade.",
            license.tier, license.max_heroes, "guild activate <key>".cyan()
        );
        println!();
        println!(
            "  {} Rookie mode is active. You will see extra guidance for the",
            "NOTE:".yellow().bold()
        );
        println!(
            "  first 7 days. Run {} to disable it early.",
            "guild config skip-rookie".cyan()
        );
    } else {
        println!("Next steps:");
        println!("  {} — register a project", "guild project add".cyan());
        println!("  {} — recruit your first hero", "guild recruit".cyan());
        println!("  {} — set your first goal", "guild goal \"...\"".cyan());
    }

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
