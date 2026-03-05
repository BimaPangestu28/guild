mod goal;
mod hero;
mod init;
mod mcp;
mod memory;
mod project;
mod quest;
pub mod secret;
mod skill;
mod status;

use anyhow::Result;
use clap::{Parser, Subcommand};
use colored::Colorize;

use crate::db;

#[derive(Parser)]
#[command(name = "guild", about = "Self-hosted multi-agent development OS")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Subcommand)]
pub enum Command {
    /// Initialize a new guild
    Init {
        /// Register a project during init
        #[arg(long)]
        project: Option<String>,
    },

    /// Set a goal for the guild
    Goal {
        /// The goal description
        description: String,
        /// Target project
        #[arg(long)]
        project: Option<String>,
    },

    /// Show guild status overview
    Status,

    /// Show recent activity log
    Log {
        /// Number of entries
        #[arg(short, long, default_value = "20")]
        count: usize,
    },

    /// Show latest Guild Master report
    Report,

    /// Show today's cost breakdown
    Cost,

    /// Manage projects
    #[command(subcommand)]
    Project(project::ProjectCommand),

    /// Recruit a new hero
    Recruit {
        /// Hero class
        #[arg(long)]
        class: Option<String>,
        /// Hero name
        #[arg(long)]
        name: Option<String>,
    },

    /// List all heroes
    Heroes,

    /// Show or manage a specific hero
    Hero {
        /// Hero name
        name: String,
        /// Start hero session
        #[arg(long)]
        start: bool,
    },

    /// Retire a hero
    Retire {
        /// Hero name
        name: String,
    },

    /// Pause hero(es)
    Pause {
        /// Hero name (or --all)
        name: Option<String>,
        #[arg(long)]
        all: bool,
    },

    /// Resume hero(es)
    Resume {
        /// Hero name (or --all)
        name: Option<String>,
        #[arg(long)]
        all: bool,
    },

    /// Manage shared and hero memory
    #[command(subcommand)]
    Memory(memory::MemoryCommand),

    /// Manage hero skills
    #[command(subcommand)]
    Skill(skill::SkillCommand),

    /// Manage MCP servers
    #[command(subcommand)]
    Mcp(mcp::McpCommand),

    /// Manage quests
    #[command(subcommand)]
    Quest(quest::QuestCommand),

    /// Show quest board
    Quests {
        /// Filter by project
        #[arg(long)]
        project: Option<String>,
        /// Filter by status
        #[arg(long)]
        status: Option<String>,
    },

    /// Assign quest to hero manually
    Assign {
        quest_id: String,
        hero_name: String,
    },

    /// Show active file locks
    Locks,

    /// Manage secrets
    #[command(subcommand)]
    Secret(secret::SecretCommand),

    /// Setup Telegram notifications
    SetupTelegram,

    /// Open local dashboard
    Dashboard,
}

pub fn run(cli: Cli) -> Result<()> {
    match cli.command {
        Command::Init { project } => init::run(project),
        Command::Goal { description, project } => goal::run(description, project),
        Command::Status => status::run_status(),
        Command::Log { count } => status::run_log(count),
        Command::Report => status::run_report(),
        Command::Cost => status::run_cost(),
        Command::Project(cmd) => project::run(cmd),
        Command::Recruit { class, name } => hero::run_recruit(class, name),
        Command::Heroes => hero::run_list(),
        Command::Hero { name, start } => hero::run_show(name, start),
        Command::Retire { name } => hero::run_retire(name),
        Command::Pause { name, all } => hero::run_pause(name, all),
        Command::Resume { name, all } => hero::run_resume(name, all),
        Command::Memory(cmd) => memory::run(cmd),
        Command::Skill(cmd) => skill::run(cmd),
        Command::Mcp(cmd) => mcp::run(cmd),
        Command::Quest(cmd) => quest::run(cmd),
        Command::Quests { project, status } => quest::run_list(project, status),
        Command::Assign { quest_id, hero_name } => quest::run_assign(quest_id, hero_name),
        Command::Secret(cmd) => secret::run(cmd),
        Command::SetupTelegram => run_setup_telegram(),
        Command::Locks => run_locks(),
        Command::Dashboard => {
            println!("Opening dashboard at http://localhost:7432 ...");
            Ok(())
        }
    }
}

fn run_setup_telegram() -> Result<()> {
    use dialoguer::Input;
    use serde_json::Value;
    use std::fs;

    println!("{}", "TELEGRAM SETUP".yellow().bold());
    println!("{}", "-".repeat(40));
    println!("  You need a Telegram Bot Token and Chat ID.");
    println!("  1. Talk to @BotFather on Telegram to create a bot");
    println!("  2. Send a message to your bot, then visit:");
    println!("     https://api.telegram.org/bot<TOKEN>/getUpdates");
    println!("     to find your chat_id.\n");

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

    // Load or create config.json
    let config_path = db::guild_dir().join("config.json");
    let mut config: Value = if config_path.exists() {
        let content = fs::read_to_string(&config_path)?;
        serde_json::from_str(&content).unwrap_or(Value::Object(serde_json::Map::new()))
    } else {
        Value::Object(serde_json::Map::new())
    };

    // Set telegram config
    let telegram = serde_json::json!({
        "bot_token": token,
        "chat_id": chat_id,
        "notification_level": notification_level.parse::<u32>().unwrap_or(3),
    });

    config.as_object_mut()
        .expect("config must be an object")
        .insert("telegram".to_string(), telegram);

    if let Some(parent) = config_path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&config_path, serde_json::to_string_pretty(&config)?)?;

    println!(
        "\n{} Telegram configured! Config saved to {}",
        "+".green(),
        config_path.display().to_string().dimmed()
    );
    println!(
        "  Run {} to start the bot.",
        "python3 agents/telegram_bot.py".cyan()
    );

    Ok(())
}

fn run_locks() -> Result<()> {
    let conn = db::open()?;
    let locks = db::get_locks(&conn)?;

    println!("{}", "FILE LOCKS".yellow().bold());
    println!("{}", "─".repeat(70));

    if locks.is_empty() {
        println!("  No active file locks.");
    } else {
        for (file_path, quest_id, hero_name, locked_at) in &locks {
            println!(
                "  {} — quest {} by {} ({})",
                file_path.cyan(),
                quest_id.dimmed(),
                hero_name.yellow(),
                locked_at.dimmed(),
            );
        }
        println!("\n  {} lock(s) active.", locks.len());
    }

    Ok(())
}
