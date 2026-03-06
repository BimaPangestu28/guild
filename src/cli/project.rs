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
    println!(
        "\n  Tip: Run {} to set up branch protection rules.",
        format!("guild project protect {}", project_name).cyan()
    );

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
