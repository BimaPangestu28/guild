mod goal;
mod hero;
mod init;
mod memory;
mod project;
mod quest;
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
        Command::Quest(cmd) => quest::run(cmd),
        Command::Quests { project, status } => quest::run_list(project, status),
        Command::Assign { quest_id, hero_name } => quest::run_assign(quest_id, hero_name),
        Command::Locks => run_locks(),
        Command::Dashboard => {
            println!("Opening dashboard at http://localhost:7432 ...");
            Ok(())
        }
    }
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
