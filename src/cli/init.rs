use anyhow::{bail, Result};
use chrono::Utc;
use colored::Colorize;
use dialoguer::{Confirm, Input};
use serde_json::Value;
use std::fs;
use std::process::Command;

use crate::db;

fn check_system_requirements() {
    println!("{}", "Checking system requirements...".dimmed());

    // Check git
    match Command::new("git").arg("--version").output() {
        Ok(output) if output.status.success() => {
            let version_str = String::from_utf8_lossy(&output.stdout);
            let version_str = version_str.trim();
            let is_v2_plus = version_str
                .split_whitespace()
                .find(|s| s.starts_with(|c: char| c.is_ascii_digit()))
                .map(|v| v.starts_with('2') || v.starts_with('3'))
                .unwrap_or(false);

            if is_v2_plus {
                println!("  {} git: {}", "OK".green(), version_str.dimmed());
            } else {
                println!(
                    "  {} git: {} (2.x+ recommended)",
                    "WARN".yellow(),
                    version_str.dimmed()
                );
            }
        }
        _ => {
            println!(
                "  {} git not found. Install git 2.x+ before using Guild.",
                "WARN".yellow()
            );
        }
    }

    // Check python3
    match Command::new("python3").arg("--version").output() {
        Ok(output) if output.status.success() => {
            let version_str = String::from_utf8_lossy(&output.stdout);
            let version_str = version_str.trim();
            let is_311_plus = version_str
                .split_whitespace()
                .find(|s| s.starts_with(|c: char| c.is_ascii_digit()))
                .and_then(|v| {
                    let parts: Vec<&str> = v.split('.').collect();
                    if parts.len() >= 2 {
                        let major = parts[0].parse::<u32>().ok()?;
                        let minor = parts[1].parse::<u32>().ok()?;
                        Some(major >= 3 && minor >= 11)
                    } else {
                        None
                    }
                })
                .unwrap_or(false);

            if is_311_plus {
                println!("  {} python3: {}", "OK".green(), version_str.dimmed());
            } else {
                println!(
                    "  {} python3: {} (3.11+ recommended)",
                    "WARN".yellow(),
                    version_str.dimmed()
                );
            }
        }
        _ => {
            println!(
                "  {} python3 not found. Install Python 3.11+ for agent runtime.",
                "WARN".yellow()
            );
        }
    }

    println!();
}

fn prompt_api_key() -> Result<bool> {
    let has_key = std::env::var("ANTHROPIC_API_KEY").is_ok();
    if has_key {
        println!("  {} ANTHROPIC_API_KEY already set in environment", "OK".green());
        return Ok(false);
    }

    let setup = Confirm::new()
        .with_prompt("Set up Anthropic API key now?")
        .default(true)
        .interact()?;

    if !setup {
        println!(
            "  {} Set ANTHROPIC_API_KEY later or run {}",
            "SKIP".yellow(),
            "guild secret add ANTHROPIC_API_KEY <value>".cyan()
        );
        return Ok(false);
    }

    let key: String = Input::new()
        .with_prompt("Anthropic API key")
        .interact_text()?;

    let key = key.trim().to_string();

    if !key.starts_with("sk-ant-") {
        println!(
            "  {} Key does not start with \"sk-ant-\". Storing anyway, but double-check the value.",
            "WARN".yellow()
        );
    }

    super::secret::run_add("ANTHROPIC_API_KEY".to_string(), key)?;
    Ok(true)
}

fn prompt_telegram_setup() -> Result<bool> {
    let setup = Confirm::new()
        .with_prompt("Set up Telegram notifications?")
        .default(false)
        .interact()?;

    if !setup {
        return Ok(false);
    }

    println!();
    println!("  You need a Telegram Bot Token and Chat ID.");
    println!("  1. Talk to @BotFather on Telegram to create a bot");
    println!("  2. Send a message to your bot, then visit:");
    println!("     https://api.telegram.org/bot<TOKEN>/getUpdates");
    println!("     to find your chat_id.");
    println!();

    let token: String = Input::new()
        .with_prompt("Bot Token")
        .interact_text()?;

    let chat_id: String = Input::new()
        .with_prompt("Chat ID")
        .interact_text()?;

    let notification_level: String = Input::new()
        .with_prompt("Notification level (1=Silent, 2=Dashboard, 3=Telegram, 4=Urgent)")
        .default("3".to_string())
        .interact_text()?;

    let config_path = db::guild_dir().join("config.json");
    let mut config: Value = if config_path.exists() {
        let content = fs::read_to_string(&config_path)?;
        serde_json::from_str(&content).unwrap_or(Value::Object(serde_json::Map::new()))
    } else {
        Value::Object(serde_json::Map::new())
    };

    let telegram = serde_json::json!({
        "bot_token": token.trim(),
        "chat_id": chat_id.trim(),
        "notification_level": notification_level.trim().parse::<u32>().unwrap_or(3),
    });

    config
        .as_object_mut()
        .expect("config must be an object")
        .insert("telegram".to_string(), telegram);

    fs::write(&config_path, serde_json::to_string_pretty(&config)?)?;
    println!("  {} Telegram configured", "OK".green());
    Ok(true)
}

fn prompt_first_hero() -> Result<bool> {
    let recruit = Confirm::new()
        .with_prompt("Recruit your first hero?")
        .default(false)
        .interact()?;

    if !recruit {
        return Ok(false);
    }

    println!();
    super::hero::run_recruit(None, None)?;
    Ok(true)
}

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

        check_system_requirements();
    }

    println!("{}", "[1/4] Creating guild workspace...".yellow());

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

    println!("  {} Directory structure created", "OK".green());

    println!("{}", "[2/4] Initializing database...".yellow());
    let db_path = guild_dir.join("guild.db");
    let conn = db::init_at(&db_path)?;
    println!("  {} SQLite database initialized", "OK".green());

    println!("{}", "[3/4] Writing default templates...".yellow());
    write_default_conventions(&guild_dir)?;
    println!("  {} Default conventions written", "OK".green());

    db::log_activity(&conn, "system", "Guild initialized", None, None, "info")?;

    if first_init {
        let config_path = guild_dir.join("config.json");
        let mut config: Value = if config_path.exists() {
            let content = fs::read_to_string(&config_path)?;
            serde_json::from_str(&content).unwrap_or(Value::Object(serde_json::Map::new()))
        } else {
            Value::Object(serde_json::Map::new())
        };

        let obj = config.as_object_mut().expect("config must be an object");
        obj.insert(
            "created_at".to_string(),
            Value::String(Utc::now().to_rfc3339()),
        );
        obj.insert("rookie_mode".to_string(), Value::Bool(true));

        fs::write(&config_path, serde_json::to_string_pretty(&config)?)?;
    }

    println!("{}", "[4/4] Done!".yellow());
    println!();
    println!("{}", "Guild initialized successfully.".green().bold());
    println!("  Location: {}", guild_dir.display());
    println!();

    if first_init {
        println!("{}", "--- Optional Setup ---".yellow().bold());
        println!();

        let api_key_stored = prompt_api_key()?;
        if api_key_stored {
            println!();
        }

        let telegram_configured = prompt_telegram_setup()?;
        if telegram_configured {
            println!();
        }

        let hero_recruited = prompt_first_hero()?;
        if hero_recruited {
            println!();
        }

        let license = crate::license::License::load();
        println!("{}", "Getting Started:".yellow().bold());
        println!("  1. {} -- register a project", "guild project add".cyan());
        if !hero_recruited {
            println!("  2. {} -- recruit your first hero", "guild recruit".cyan());
        }
        println!(
            "  3. {} -- set your first goal",
            "guild goal \"...\"".cyan()
        );
        println!(
            "  4. {} -- check guild status anytime",
            "guild status".cyan()
        );
        println!();
        println!(
            "  License: {:?} (max {} heroes). Use {} to upgrade.",
            license.tier,
            license.max_heroes,
            "guild activate <key>".cyan()
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
        println!("  {} -- register a project", "guild project add".cyan());
        println!("  {} -- recruit your first hero", "guild recruit".cyan());
        println!(
            "  {} -- set your first goal",
            "guild goal \"...\"".cyan()
        );
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
         - `feature/GLD-{id}-{slug}` -- new features\n\
         - `fix/GLD-{id}-{slug}` -- bug fixes\n\
         - `chore/GLD-{id}-{slug}` -- maintenance\n\n\
         ## Commit Format\n\
         ```\n\
         [GLD-{id}] {short description} -- {hero_name}\n\
         ```\n\n\
         ## Rules\n\
         - Branches always from `development`, never from `main`\n\
         - PRs always target `development`\n\
         - `development` -> `main` requires human approval\n\
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
