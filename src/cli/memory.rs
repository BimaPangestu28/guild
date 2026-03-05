use anyhow::{bail, Result};
use clap::Subcommand;
use colored::Colorize;
use std::path::PathBuf;

use crate::db;

#[derive(Subcommand)]
pub enum MemoryCommand {
    /// Show shared memory index
    Show {
        #[arg(long)]
        project: Option<String>,
        #[arg(long)]
        hero: Option<String>,
        #[arg(long)]
        adr: Option<String>,
    },
    /// Edit memory file in $EDITOR
    Edit {
        #[arg(long)]
        project: Option<String>,
        #[arg(long)]
        hero: Option<String>,
        #[arg(long, default_value = "notes")]
        file: String,
    },
    /// Clear hero private memory
    Clear {
        #[arg(long)]
        hero: String,
    },
    /// Export all memory to a directory
    Export {
        #[arg(long)]
        output: String,
    },
    /// Import memory from a directory
    Import {
        path: String,
    },
}

pub fn run(cmd: MemoryCommand) -> Result<()> {
    match cmd {
        MemoryCommand::Show { project, hero, adr } => run_show(project, hero, adr),
        MemoryCommand::Edit { project, hero, file } => run_edit(project, hero, file),
        MemoryCommand::Clear { hero } => run_clear(hero),
        MemoryCommand::Export { output } => run_export(output),
        MemoryCommand::Import { path } => run_import(path),
    }
}

fn memory_dir() -> PathBuf {
    db::guild_dir().join("workspace/memory")
}

fn run_show(project: Option<String>, hero: Option<String>, adr: Option<String>) -> Result<()> {
    let mem = memory_dir();

    match (project.as_deref(), hero.as_deref(), adr.as_deref()) {
        // No flags: list all shared memory files
        (None, None, None) => {
            let shared_dir = mem.join("shared");
            if !shared_dir.exists() {
                bail!("Shared memory directory does not exist: {}", shared_dir.display());
            }

            println!("{}", "SHARED MEMORY".yellow().bold());
            println!("{}", "─".repeat(60));
            list_files_recursive(&shared_dir, &shared_dir)?;
        }

        // --project: read project memory file
        (Some(name), None, None) => {
            let path = mem.join(format!("shared/projects/{}.md", name));
            if !path.exists() {
                bail!("No memory file for project '{}'", name);
            }
            let content = std::fs::read_to_string(&path)?;
            println!("{}", content);
        }

        // --hero: read hero's notes.md
        (None, Some(name), None) => {
            let path = mem.join(format!("heroes/{}/notes.md", name));
            if !path.exists() {
                bail!("No memory file for hero '{}'", name);
            }
            let content = std::fs::read_to_string(&path)?;
            println!("{}", content);
        }

        // --project + --adr: read specific ADR file
        (Some(proj), None, Some(adr_name)) => {
            let path = mem.join(format!("shared/projects/{}-adr/{}.md", proj, adr_name));
            if !path.exists() {
                bail!("ADR '{}' not found for project '{}'", adr_name, proj);
            }
            let content = std::fs::read_to_string(&path)?;
            println!("{}", content);
        }

        _ => {
            bail!("Invalid flag combination. Use --project, --hero, or --project with --adr.");
        }
    }

    Ok(())
}

fn list_files_recursive(dir: &std::path::Path, base: &std::path::Path) -> Result<()> {
    if !dir.is_dir() {
        return Ok(());
    }

    let mut entries: Vec<_> = std::fs::read_dir(dir)?
        .filter_map(|e| e.ok())
        .collect();
    entries.sort_by_key(|e| e.file_name());

    for entry in entries {
        let path = entry.path();
        let relative = path.strip_prefix(base).unwrap_or(&path);

        if path.is_dir() {
            println!("  {}/", relative.display().to_string().cyan());
            list_files_recursive(&path, base)?;
        } else {
            println!("  {}", relative.display().to_string().dimmed());
        }
    }

    Ok(())
}

fn run_edit(project: Option<String>, hero: Option<String>, file: String) -> Result<()> {
    let mem = memory_dir();

    let target = match (project.as_deref(), hero.as_deref()) {
        (Some(name), None) => {
            mem.join(format!("shared/projects/{}.md", name))
        }
        (None, Some(name)) => {
            mem.join(format!("heroes/{}/{}.md", name, file))
        }
        (None, None) => {
            bail!("Specify --project or --hero to edit.");
        }
        _ => {
            bail!("Specify either --project or --hero, not both.");
        }
    };

    if !target.exists() {
        bail!("File does not exist: {}", target.display());
    }

    let editor = std::env::var("EDITOR").unwrap_or_else(|_| "vi".into());
    let status = std::process::Command::new(&editor)
        .arg(&target)
        .status()?;

    if !status.success() {
        bail!("Editor exited with non-zero status");
    }

    println!("{} Saved {}", "✓".green(), target.display());
    Ok(())
}

fn run_clear(hero: String) -> Result<()> {
    let mem = memory_dir();
    let path = mem.join(format!("heroes/{}/notes.md", hero));

    if !path.exists() {
        bail!("No memory file for hero '{}'", hero);
    }

    let confirm = dialoguer::Confirm::new()
        .with_prompt(format!("Clear all notes for hero '{}'?", hero))
        .default(false)
        .interact()?;

    if !confirm {
        println!("Cancelled.");
        return Ok(());
    }

    std::fs::write(&path, "# Notes\n")?;
    println!("{} Cleared notes for hero '{}'", "✓".green(), hero);
    Ok(())
}

fn run_export(output: String) -> Result<()> {
    let mem = memory_dir();
    if !mem.exists() {
        bail!("Memory directory does not exist: {}", mem.display());
    }

    let dest = PathBuf::from(&output);
    if dest.exists() {
        bail!("Output path already exists: {}", dest.display());
    }

    copy_dir_recursive(&mem, &dest)?;
    println!("{} Exported memory to {}", "✓".green(), dest.display());
    Ok(())
}

fn run_import(path: String) -> Result<()> {
    let source = PathBuf::from(&path);
    if !source.exists() {
        bail!("Source path does not exist: {}", source.display());
    }

    let mem = memory_dir();
    copy_dir_recursive(&source, &mem)?;
    println!("{} Imported memory from {}", "✓".green(), source.display());
    Ok(())
}

fn copy_dir_recursive(src: &std::path::Path, dst: &std::path::Path) -> Result<()> {
    std::fs::create_dir_all(dst)?;

    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let src_path = entry.path();
        let dst_path = dst.join(entry.file_name());

        if src_path.is_dir() {
            copy_dir_recursive(&src_path, &dst_path)?;
        } else {
            std::fs::copy(&src_path, &dst_path)?;
        }
    }

    Ok(())
}
