use anyhow::{bail, Result};
use chrono::Utc;
use clap::Subcommand;
use colored::Colorize;
use std::path::PathBuf;

use crate::db;

#[derive(Subcommand)]
pub enum ProjectCommand {
    /// Register a new project
    Add {
        /// Path to the project repository
        #[arg(long)]
        path: Option<String>,
        /// Short project name
        #[arg(long)]
        name: Option<String>,
        /// Git provider (github/gitlab/none)
        #[arg(long)]
        provider: Option<String>,
        /// Main branch name
        #[arg(long, name = "main")]
        main_branch: Option<String>,
        /// Development branch name
        #[arg(long, name = "dev")]
        dev_branch: Option<String>,
    },
    /// List all projects
    List,
    /// Show project details
    Show { name: String },
    /// Pause a project
    Pause { name: String },
    /// Resume a paused project
    Resume { name: String },
    /// Archive a project
    Archive { name: String },
    /// Unarchive a project
    Unarchive { name: String },
    /// Remove a project from guild
    Remove { name: String },
    /// Show project health report
    Health { name: String },
}

pub fn run(cmd: ProjectCommand) -> Result<()> {
    match cmd {
        ProjectCommand::Add {
            path,
            name,
            provider,
            main_branch,
            dev_branch,
        } => run_add(path, name, provider, main_branch, dev_branch),
        ProjectCommand::List => run_list(),
        ProjectCommand::Show { name } => run_show(&name),
        ProjectCommand::Pause { name } => run_set_status(&name, "paused"),
        ProjectCommand::Resume { name } => run_set_status(&name, "active"),
        ProjectCommand::Archive { name } => run_set_status(&name, "archived"),
        ProjectCommand::Unarchive { name } => run_set_status(&name, "active"),
        ProjectCommand::Remove { name } => run_remove(&name),
        ProjectCommand::Health { name } => {
            println!("Health report for {} — coming soon", name);
            Ok(())
        }
    }
}

fn run_add(
    path: Option<String>,
    name: Option<String>,
    provider: Option<String>,
    main_branch: Option<String>,
    dev_branch: Option<String>,
) -> Result<()> {
    let conn = db::open()?;

    // Resolve path
    let project_path = match path {
        Some(p) => PathBuf::from(&p).canonicalize()?,
        None => {
            let input: String = dialoguer::Input::new()
                .with_prompt("Project path")
                .interact_text()?;
            PathBuf::from(&input).canonicalize()?
        }
    };

    // Verify it's a git repo
    if !project_path.join(".git").exists() {
        bail!("{} is not a git repository", project_path.display());
    }

    // Get project name
    let project_name = match name {
        Some(n) => n,
        None => {
            let default = project_path
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default();
            dialoguer::Input::new()
                .with_prompt("Project name")
                .default(default)
                .interact_text()?
        }
    };

    // Detect language
    let language = detect_language(&project_path);

    let main_b = main_branch.unwrap_or_else(|| "main".into());
    let dev_b = dev_branch.unwrap_or_else(|| "development".into());
    let prov = provider.unwrap_or_else(|| "none".into());
    let display_name = project_name.clone();
    let id = uuid::Uuid::new_v4().to_string();
    let now = Utc::now().to_rfc3339();

    conn.execute(
        "INSERT INTO projects (id, name, display_name, path, repo_provider, main_branch, dev_branch, language, created_at, last_active) \
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
        rusqlite::params![id, project_name, display_name, project_path.to_string_lossy(), prov, main_b, dev_b, language, now, now],
    )?;

    // Create shared memory files
    let guild_dir = db::guild_dir();
    let mem_dir = guild_dir.join("workspace/memory/shared/projects");
    std::fs::write(
        mem_dir.join(format!("{}.md", project_name)),
        format!("# {}\n\nProject knowledge base.\n", display_name),
    )?;
    std::fs::create_dir_all(mem_dir.join(format!("{}-adr", project_name)))?;

    db::log_activity(
        &conn,
        "system",
        &format!("Project '{}' registered", project_name),
        None,
        Some(&id),
        "info",
    )?;

    println!("{} Project '{}' registered", "✓".green(), project_name);
    if let Some(lang) = &language {
        println!("  Language: {}", lang);
    }
    println!("  Path: {}", project_path.display());
    println!("  Branches: {} → {}", main_b, dev_b);

    Ok(())
}

fn run_list() -> Result<()> {
    let conn = db::open()?;
    let mut stmt = conn.prepare("SELECT name, display_name, language, status, path FROM projects ORDER BY name")?;
    let rows = stmt.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, Option<String>>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, String>(4)?,
        ))
    })?;

    println!("{}", "PROJECTS".yellow().bold());
    println!("{}", "─".repeat(60));

    let mut count = 0;
    for row in rows {
        let (name, display, lang, status, path) = row?;
        let status_colored = match status.as_str() {
            "active" => status.green(),
            "paused" => status.yellow(),
            "archived" => status.dimmed(),
            _ => status.normal(),
        };
        println!(
            "  {} {} [{}] {}",
            name.cyan().bold(),
            lang.unwrap_or_default().dimmed(),
            status_colored,
            path.dimmed()
        );
        let _ = display; // used for detailed view
        count += 1;
    }

    if count == 0 {
        println!("  No projects registered. Use {} to add one.", "guild project add".cyan());
    }

    Ok(())
}

fn run_show(name: &str) -> Result<()> {
    let conn = db::open()?;
    let row = conn.query_row(
        "SELECT name, display_name, path, language, status, main_branch, dev_branch, repo_provider, created_at FROM projects WHERE name = ?1",
        [name],
        |row| Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, Option<String>>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, String>(5)?,
            row.get::<_, String>(6)?,
            row.get::<_, Option<String>>(7)?,
            row.get::<_, String>(8)?,
        ))
    );

    match row {
        Ok((name, display, path, lang, status, main_b, dev_b, provider, created)) => {
            println!("{} {}", "Project:".yellow(), display.bold());
            println!("  Name:     {}", name);
            println!("  Path:     {}", path);
            println!("  Language: {}", lang.unwrap_or_else(|| "unknown".into()));
            println!("  Status:   {}", status);
            println!("  Branches: {} → {}", main_b, dev_b);
            println!("  Provider: {}", provider.unwrap_or_else(|| "none".into()));
            println!("  Created:  {}", created);
        }
        Err(_) => bail!("Project '{}' not found", name),
    }

    Ok(())
}

fn run_set_status(name: &str, status: &str) -> Result<()> {
    let conn = db::open()?;
    let updated = conn.execute(
        "UPDATE projects SET status = ?1 WHERE name = ?2",
        rusqlite::params![status, name],
    )?;
    if updated == 0 {
        bail!("Project '{}' not found", name);
    }
    println!("{} Project '{}' is now {}", "✓".green(), name, status);
    Ok(())
}

fn run_remove(name: &str) -> Result<()> {
    let conn = db::open()?;

    let confirm = dialoguer::Confirm::new()
        .with_prompt(format!("Remove project '{}'? This won't delete local files.", name))
        .default(false)
        .interact()?;

    if !confirm {
        println!("Cancelled.");
        return Ok(());
    }

    let deleted = conn.execute("DELETE FROM projects WHERE name = ?1", [name])?;
    if deleted == 0 {
        bail!("Project '{}' not found", name);
    }
    println!("{} Project '{}' removed from guild", "✓".green(), name);
    Ok(())
}

fn detect_language(path: &std::path::Path) -> Option<String> {
    let checks = [
        ("Cargo.toml", "Rust"),
        ("package.json", "TypeScript/JavaScript"),
        ("pyproject.toml", "Python"),
        ("requirements.txt", "Python"),
        ("go.mod", "Go"),
        ("pom.xml", "Java"),
        ("build.gradle", "Java"),
        ("Gemfile", "Ruby"),
        ("mix.exs", "Elixir"),
    ];

    for (file, lang) in checks {
        if path.join(file).exists() {
            return Some(lang.to_string());
        }
    }
    None
}
