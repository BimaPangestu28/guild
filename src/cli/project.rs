use anyhow::{bail, Result};
use chrono::Utc;
use clap::Subcommand;
use colored::Colorize;
use std::path::PathBuf;
use std::process::{Command, Stdio};

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
    /// Set up branch protection rules
    Protect { name: String },
    /// Edit project memory file in $EDITOR
    Edit { name: String },
    /// Manage project MCP servers
    #[command(subcommand)]
    Mcp(ProjectMcpAction),
    /// Manage project groups
    #[command(subcommand)]
    Group(GroupAction),
}

#[derive(Subcommand)]
pub enum GroupAction {
    /// Create a new project group
    Create { name: String },
    /// Add a project to a group
    Add { group: String, project: String },
    /// List all project groups
    List,
    /// Show projects in a group
    Show { name: String },
    /// Remove a project group
    Remove { name: String },
}

#[derive(Subcommand)]
pub enum ProjectMcpAction {
    /// Add an MCP server to a project
    Add {
        /// Project name
        project: String,
        /// MCP server name
        mcp: String,
    },
    /// Remove an MCP server from a project
    Remove {
        /// Project name
        project: String,
        /// MCP server name
        mcp: String,
    },
    /// List MCP servers for a project
    List {
        /// Project name
        project: String,
    },
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
        ProjectCommand::Protect { name } => run_protect(&name),
        ProjectCommand::Edit { name } => run_edit(&name),
        ProjectCommand::Mcp(action) => run_mcp(action),
        ProjectCommand::Group(action) => run_group(action),
    }
}

pub(crate) fn run_add(
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

    // Ensure dev branch exists, create from main if needed
    let check = Command::new("git")
        .args(["-C", &project_path.to_string_lossy(), "rev-parse", "--verify", &dev_b])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .output();

    if let Ok(output) = check {
        if !output.status.success() {
            // Dev branch doesn't exist, create from main
            println!("  Creating '{}' branch from '{}'...", dev_b, main_b);
            let _ = Command::new("git")
                .args(["-C", &project_path.to_string_lossy(), "branch", &dev_b, &main_b])
                .status();
        }
    }

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

    let _ = write_project_config(
        &guild_dir,
        &project_name,
        &project_path.to_string_lossy(),
        &prov,
        &main_b,
        &dev_b,
        language.as_deref().unwrap_or("unknown"),
    );

    let _ = scan_conventions(
        &project_path.to_string_lossy(),
        &project_name,
        &guild_dir,
    );

    println!(
        "\n  Tip: Run {} to set up branch protection rules.",
        format!("guild project protect {}", project_name).cyan()
    );

    Ok(())
}

fn run_edit(name: &str) -> Result<()> {
    let guild_dir = db::guild_dir();
    let project_file = guild_dir
        .join("workspace/memory/shared/projects")
        .join(format!("{}.md", name));

    if !project_file.exists() {
        bail!("Project memory file not found: {}", project_file.display());
    }

    let editor = std::env::var("EDITOR").unwrap_or_else(|_| "vi".to_string());
    Command::new(&editor)
        .arg(&project_file)
        .status()?;

    println!("{} Project '{}' memory updated", "✓".green(), name.cyan());
    Ok(())
}

fn run_mcp(action: ProjectMcpAction) -> Result<()> {
    let conn = db::open()?;
    match action {
        ProjectMcpAction::Add { project, mcp } => {
            let mcp_exists: bool = conn
                .query_row(
                    "SELECT COUNT(*) FROM mcp_servers WHERE name = ?1",
                    [&mcp],
                    |row| row.get::<_, i64>(0),
                )
                .map(|c| c > 0)
                .unwrap_or(false);

            if !mcp_exists {
                bail!(
                    "MCP '{}' not found. Use `guild mcp list` to see available MCPs.",
                    mcp
                );
            }

            let current: String = conn
                .query_row(
                    "SELECT COALESCE(default_mcps, '') FROM projects WHERE name = ?1",
                    [&project],
                    |row| row.get(0),
                )
                .map_err(|_| anyhow::anyhow!("Project '{}' not found", project))?;

            let mut mcps: Vec<String> = if current.is_empty() {
                vec![]
            } else {
                current.split(',').map(|s| s.trim().to_string()).collect()
            };

            if !mcps.contains(&mcp) {
                mcps.push(mcp.clone());
            }

            conn.execute(
                "UPDATE projects SET default_mcps = ?1 WHERE name = ?2",
                rusqlite::params![mcps.join(","), project],
            )?;

            db::log_activity(
                &conn,
                "system",
                &format!("MCP '{}' attached to project '{}'", mcp, project),
                None,
                None,
                "info",
            )?;

            println!(
                "{} MCP '{}' attached to project '{}'",
                "✓".green(),
                mcp.cyan(),
                project.bold()
            );
        }
        ProjectMcpAction::Remove { project, mcp } => {
            let current: String = conn
                .query_row(
                    "SELECT COALESCE(default_mcps, '') FROM projects WHERE name = ?1",
                    [&project],
                    |row| row.get(0),
                )
                .map_err(|_| anyhow::anyhow!("Project '{}' not found", project))?;

            let mcps: Vec<String> = current
                .split(',')
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty() && s != &mcp)
                .collect();

            conn.execute(
                "UPDATE projects SET default_mcps = ?1 WHERE name = ?2",
                rusqlite::params![mcps.join(","), project],
            )?;

            db::log_activity(
                &conn,
                "system",
                &format!("MCP '{}' detached from project '{}'", mcp, project),
                None,
                None,
                "info",
            )?;

            println!(
                "{} MCP '{}' detached from project '{}'",
                "✓".green(),
                mcp.cyan(),
                project.bold()
            );
        }
        ProjectMcpAction::List { project } => {
            let current: String = conn
                .query_row(
                    "SELECT COALESCE(default_mcps, '') FROM projects WHERE name = ?1",
                    [&project],
                    |row| row.get(0),
                )
                .map_err(|_| anyhow::anyhow!("Project '{}' not found", project))?;

            let mcps: Vec<String> = current
                .split(',')
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect();

            println!(
                "{} {}",
                "MCP SERVERS FOR".yellow().bold(),
                project.cyan().bold()
            );
            println!("{}", "─".repeat(50));

            if mcps.is_empty() {
                println!(
                    "  No MCPs attached. Use {} to add one.",
                    format!("guild project mcp add {} <mcp>", project).cyan()
                );
            } else {
                for mcp in &mcps {
                    println!("  {}", mcp.bold());
                }
                println!("\n  {} MCP(s) attached.", mcps.len());
            }
        }
    }
    Ok(())
}

fn scan_conventions(path: &str, project_name: &str, guild_dir: &std::path::Path) -> Result<()> {
    let conventions_dir = guild_dir.join("workspace/memory/shared/conventions");
    std::fs::create_dir_all(&conventions_dir)?;
    let mut found = Vec::new();

    let config_files = [
        (".editorconfig", "EditorConfig"),
        (".eslintrc", "ESLint"),
        (".eslintrc.json", "ESLint"),
        (".eslintrc.js", "ESLint"),
        (".prettierrc", "Prettier"),
        (".prettierrc.json", "Prettier"),
        ("tsconfig.json", "TypeScript"),
        ("rustfmt.toml", "Rustfmt"),
        (".rustfmt.toml", "Rustfmt"),
        ("pyproject.toml", "Python Project"),
        ("setup.cfg", "Python Setup"),
        (".clippy.toml", "Clippy"),
        ("Makefile", "Make"),
        ("Justfile", "Just"),
    ];

    for (filename, tool_name) in &config_files {
        let file_path = std::path::Path::new(path).join(filename);
        if file_path.exists() {
            found.push(format!("- {} ({})", tool_name, filename));
        }
    }

    if !found.is_empty() {
        let conventions_file = conventions_dir.join(format!("{}.md", project_name));
        let content = format!(
            "# {} Conventions\n\nDetected config files:\n{}\n",
            project_name,
            found.join("\n")
        );
        std::fs::write(&conventions_file, content)?;
        println!(
            "  {} Found {} convention files",
            "→".cyan(),
            found.len()
        );
    }

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

fn run_protect(name: &str) -> Result<()> {
    let conn = db::open()?;
    let row = conn.query_row(
        "SELECT path, repo_provider, main_branch, dev_branch FROM projects WHERE name = ?1",
        [name],
        |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, Option<String>>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
            ))
        },
    );

    let (path, provider, main_branch, dev_branch) = match row {
        Ok(r) => r,
        Err(_) => bail!("Project '{}' not found", name),
    };

    let provider = provider.unwrap_or_else(|| "none".into());

    // Ensure dev branch exists, create from main if not
    ensure_branch_exists(&path, &dev_branch, &main_branch)?;

    match provider.as_str() {
        "github" => protect_github(&path, &main_branch, &dev_branch)?,
        "gitlab" => protect_gitlab(&path, &main_branch, &dev_branch)?,
        _ => {
            println!("{}", "Manual branch protection setup required.".yellow());
            println!("  Configure these rules in your repository settings:");
            println!("  Branch '{}':", main_branch);
            println!("    - Require pull request before merging");
            println!("    - Require at least 1 approval");
            println!("    - Dismiss stale reviews on new commits");
            println!("    - Do not allow direct pushes");
            println!("  Branch '{}':", dev_branch);
            println!("    - Require pull request before merging");
            println!("    - Require status checks to pass");
            println!("    - Do not allow direct pushes");
        }
    }

    Ok(())
}

fn ensure_branch_exists(path: &str, branch: &str, base: &str) -> Result<()> {
    let check = Command::new("git")
        .args(["-C", path, "rev-parse", "--verify", branch])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    if let Ok(status) = check {
        if status.success() {
            return Ok(());
        }
    }

    // Check remote
    let remote_check = Command::new("git")
        .args(["-C", path, "ls-remote", "--heads", "origin", branch])
        .output()?;

    if !String::from_utf8_lossy(&remote_check.stdout).trim().is_empty() {
        return Ok(());
    }

    // Branch doesn't exist anywhere, create from base
    println!(
        "  Creating branch '{}' from '{}'...",
        branch.cyan(),
        base
    );
    let status = Command::new("git")
        .args(["-C", path, "branch", branch, base])
        .status()?;
    if !status.success() {
        println!(
            "  {} Could not create branch '{}' (non-blocking)",
            "Warning:".yellow(),
            branch
        );
    } else {
        // Push the new branch
        let push = Command::new("git")
            .args(["-C", path, "push", "-u", "origin", branch])
            .status();
        if let Ok(s) = push {
            if !s.success() {
                println!(
                    "  {} Could not push branch '{}' to origin (non-blocking)",
                    "Warning:".yellow(),
                    branch
                );
            }
        }
    }
    Ok(())
}

fn parse_github_remote(url: &str) -> Result<(String, String)> {
    // Match HTTPS: https://github.com/owner/repo.git or https://github.com/owner/repo
    // Match SSH: git@github.com:owner/repo.git or git@github.com:owner/repo
    let re = regex::Regex::new(r"[:/]([^/]+)/([^/.]+?)(?:\.git)?$")?;
    if let Some(caps) = re.captures(url) {
        Ok((caps[1].to_string(), caps[2].to_string()))
    } else {
        bail!("Could not parse owner/repo from remote URL: {}", url)
    }
}

fn protect_github(path: &str, main_branch: &str, dev_branch: &str) -> Result<()> {
    let output = Command::new("git")
        .args(["-C", path, "remote", "get-url", "origin"])
        .output()?;
    if !output.status.success() {
        bail!("Could not get git remote URL");
    }
    let remote_url = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let (owner, repo) = parse_github_remote(&remote_url)?;

    println!(
        "Setting up GitHub branch protection for {}/{}...",
        owner.cyan(),
        repo.cyan()
    );

    // Protect main: require PR reviews (1 approval), dismiss stale reviews, no direct push
    let main_rules = serde_json::json!({
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": true
        },
        "enforce_admins": false,
        "required_status_checks": null,
        "restrictions": null
    });

    let mut child = Command::new("gh")
        .args([
            "api",
            &format!("repos/{}/{}/branches/{}/protection", owner, repo, main_branch),
            "-X", "PUT",
            "-H", "Accept: application/vnd.github+json",
            "--input", "-",
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .current_dir(path)
        .spawn()?;

    if let Some(mut stdin) = child.stdin.take() {
        use std::io::Write;
        stdin.write_all(main_rules.to_string().as_bytes())?;
    }

    let output = child.wait_with_output()?;
    if output.status.success() {
        println!(
            "  {} Branch '{}' protected (require PR, 1 approval, dismiss stale reviews)",
            "✓".green(),
            main_branch
        );
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        println!(
            "  {} Failed to protect '{}': {}",
            "Warning:".yellow(),
            main_branch,
            stderr.trim()
        );
    }

    // Protect dev: require PR reviews (1 approval), require status checks, no direct push
    let dev_rules = serde_json::json!({
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": false
        },
        "enforce_admins": false,
        "required_status_checks": {
            "strict": true,
            "contexts": []
        },
        "restrictions": null
    });

    let mut child = Command::new("gh")
        .args([
            "api",
            &format!("repos/{}/{}/branches/{}/protection", owner, repo, dev_branch),
            "-X", "PUT",
            "-H", "Accept: application/vnd.github+json",
            "--input", "-",
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .current_dir(path)
        .spawn()?;

    if let Some(mut stdin) = child.stdin.take() {
        use std::io::Write;
        stdin.write_all(dev_rules.to_string().as_bytes())?;
    }

    let output = child.wait_with_output()?;
    if output.status.success() {
        println!(
            "  {} Branch '{}' protected (require PR, status checks)",
            "✓".green(),
            dev_branch
        );
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        println!(
            "  {} Failed to protect '{}': {}",
            "Warning:".yellow(),
            dev_branch,
            stderr.trim()
        );
    }

    Ok(())
}

fn protect_gitlab(path: &str, main_branch: &str, dev_branch: &str) -> Result<()> {
    let output = Command::new("git")
        .args(["-C", path, "remote", "get-url", "origin"])
        .output()?;
    if !output.status.success() {
        bail!("Could not get git remote URL");
    }
    let remote_url = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let (owner, repo) = parse_github_remote(&remote_url)?;
    let project_id = format!("{}/{}", owner, repo);
    let encoded_project = urlencoding::encode(&project_id);

    println!(
        "Setting up GitLab branch protection for {}/{}...",
        owner.cyan(),
        repo.cyan()
    );

    // Unprotect first to allow re-running (best-effort)
    for branch in [main_branch, dev_branch] {
        let encoded_branch = urlencoding::encode(branch);
        let _ = Command::new("glab")
            .args([
                "api", "-X", "DELETE",
                &format!("/projects/{}/protected_branches/{}", encoded_project, encoded_branch),
            ])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .current_dir(path)
            .status();
    }

    // main branch: no direct push, maintainers merge
    let status = Command::new("glab")
        .args([
            "api", "-X", "POST",
            &format!("/projects/{}/protected_branches", encoded_project),
            "-f", &format!("name={}", main_branch),
            "-f", "push_access_level=0",
            "-f", "merge_access_level=40",
            "-f", "allow_force_push=false",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .current_dir(path)
        .output()?;

    if status.status.success() {
        println!(
            "  {} Branch '{}' protected (no push, maintainers merge)",
            "✓".green(),
            main_branch
        );
    } else {
        let stderr = String::from_utf8_lossy(&status.stderr);
        println!(
            "  {} Failed to protect '{}': {}",
            "Warning:".yellow(),
            main_branch,
            stderr.trim()
        );
    }

    // dev branch: no direct push, developers merge
    let status = Command::new("glab")
        .args([
            "api", "-X", "POST",
            &format!("/projects/{}/protected_branches", encoded_project),
            "-f", &format!("name={}", dev_branch),
            "-f", "push_access_level=0",
            "-f", "merge_access_level=30",
            "-f", "allow_force_push=false",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .current_dir(path)
        .output()?;

    if status.status.success() {
        println!(
            "  {} Branch '{}' protected (no push, developers merge)",
            "✓".green(),
            dev_branch
        );
    } else {
        let stderr = String::from_utf8_lossy(&status.stderr);
        println!(
            "  {} Failed to protect '{}': {}",
            "Warning:".yellow(),
            dev_branch,
            stderr.trim()
        );
    }

    Ok(())
}

fn run_group(action: GroupAction) -> Result<()> {
    match action {
        GroupAction::Create { name } => run_group_create(name),
        GroupAction::Add { group, project } => run_group_add(group, project),
        GroupAction::List => run_group_list(),
        GroupAction::Show { name } => run_group_show(name),
        GroupAction::Remove { name } => run_group_remove(name),
    }
}

fn run_group_create(name: String) -> Result<()> {
    let conn = db::open()?;
    let id = uuid::Uuid::new_v4().to_string();
    let now = chrono::Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO project_groups (id, name, created_at) VALUES (?1, ?2, ?3)",
        rusqlite::params![id, name, now],
    )?;
    println!("{} Created project group '{}'", "+".green(), name.cyan());
    Ok(())
}

fn run_group_add(group: String, project: String) -> Result<()> {
    let conn = db::open()?;
    let group_id: String = conn
        .query_row(
            "SELECT id FROM project_groups WHERE name = ?1",
            [&group],
            |row| row.get(0),
        )
        .map_err(|_| anyhow::anyhow!("Group '{}' not found", group))?;

    let project_id: String = conn
        .query_row(
            "SELECT id FROM projects WHERE name = ?1",
            [&project],
            |row| row.get(0),
        )
        .map_err(|_| anyhow::anyhow!("Project '{}' not found", project))?;

    conn.execute(
        "INSERT OR IGNORE INTO project_group_members (group_id, project_id) VALUES (?1, ?2)",
        rusqlite::params![group_id, project_id],
    )?;
    println!(
        "{} Added '{}' to group '{}'",
        "+".green(),
        project.cyan(),
        group.cyan()
    );
    Ok(())
}

fn run_group_list() -> Result<()> {
    let conn = db::open()?;
    let mut stmt = conn.prepare(
        "SELECT g.name, COUNT(m.project_id) as count \
         FROM project_groups g \
         LEFT JOIN project_group_members m ON g.id = m.group_id \
         GROUP BY g.id ORDER BY g.name",
    )?;
    let rows = stmt.query_map([], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
    })?;

    println!("{}", "PROJECT GROUPS".yellow().bold());
    for row in rows {
        let (name, count) = row?;
        println!("  {} ({} projects)", name.cyan(), count);
    }
    Ok(())
}

fn run_group_show(name: String) -> Result<()> {
    let conn = db::open()?;
    let group_id: String = conn
        .query_row(
            "SELECT id FROM project_groups WHERE name = ?1",
            [&name],
            |row| row.get(0),
        )
        .map_err(|_| anyhow::anyhow!("Group '{}' not found", name))?;

    println!("{} {}", "GROUP:".yellow().bold(), name.cyan());

    let mut stmt = conn.prepare(
        "SELECT p.name, p.language, p.status \
         FROM projects p \
         JOIN project_group_members m ON p.id = m.project_id \
         WHERE m.group_id = ?1",
    )?;
    let rows = stmt.query_map([&group_id], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, Option<String>>(1)?,
            row.get::<_, String>(2)?,
        ))
    })?;

    for row in rows {
        let (pname, lang, status) = row?;
        println!(
            "  {} [{}] {}",
            pname.cyan(),
            lang.unwrap_or_default(),
            status.dimmed()
        );
    }
    Ok(())
}

fn run_group_remove(name: String) -> Result<()> {
    let conn = db::open()?;
    let group_id: String = conn
        .query_row(
            "SELECT id FROM project_groups WHERE name = ?1",
            [&name],
            |row| row.get(0),
        )
        .map_err(|_| anyhow::anyhow!("Group '{}' not found", name))?;

    conn.execute(
        "DELETE FROM project_group_members WHERE group_id = ?1",
        [&group_id],
    )?;
    conn.execute("DELETE FROM project_groups WHERE id = ?1", [&group_id])?;
    println!("{} Removed group '{}'", "-".red(), name.cyan());
    Ok(())
}

fn write_project_config(
    guild_dir: &std::path::Path,
    name: &str,
    path: &str,
    provider: &str,
    main_branch: &str,
    dev_branch: &str,
    language: &str,
) -> Result<()> {
    let config_dir = guild_dir.join("workspace/projects").join(name);
    std::fs::create_dir_all(&config_dir)?;

    let content = format!(
        "# {} Configuration\n\n\
        Path: {}\n\
        Provider: {}\n\
        Main branch: {}\n\
        Dev branch: {}\n\
        Language: {}\n\
        Registered: {}\n",
        name,
        path,
        provider,
        main_branch,
        dev_branch,
        language,
        chrono::Utc::now().format("%Y-%m-%d")
    );

    std::fs::write(config_dir.join("config.md"), content)?;
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
