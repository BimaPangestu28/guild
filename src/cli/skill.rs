use anyhow::{bail, Result};
use chrono::Utc;
use clap::Subcommand;
use colored::Colorize;

use crate::db;

#[derive(Subcommand)]
pub enum SkillCommand {
    /// List all skills for a hero
    List {
        /// Hero name
        hero: String,
    },
    /// Show detail for a specific skill
    Show {
        /// Hero name
        hero: String,
        /// Skill name
        skill: String,
    },
    /// Add a skill to a hero
    Add {
        /// Hero name
        hero: String,
        /// Skill name
        skill: String,
    },
    /// Remove a skill from a hero
    Remove {
        /// Hero name
        hero: String,
        /// Skill name
        skill: String,
    },
    /// Transfer a skill from one hero to another
    Transfer {
        /// Source hero name
        from_hero: String,
        /// Target hero name
        to_hero: String,
        /// Skill name
        skill: String,
    },
    /// Edit a skill file in $EDITOR
    Edit {
        /// Hero name
        hero: String,
        /// Skill name
        skill: String,
    },
}

pub fn run(cmd: SkillCommand) -> Result<()> {
    match cmd {
        SkillCommand::List { hero } => run_list(hero),
        SkillCommand::Show { hero, skill } => run_show(hero, skill),
        SkillCommand::Add { hero, skill } => run_add(hero, skill),
        SkillCommand::Remove { hero, skill } => run_remove(hero, skill),
        SkillCommand::Transfer { from_hero, to_hero, skill } => run_transfer(from_hero, to_hero, skill),
        SkillCommand::Edit { hero, skill } => run_edit(hero, skill),
    }
}

fn resolve_hero(conn: &rusqlite::Connection, name: &str) -> Result<(String, String)> {
    conn.query_row(
        "SELECT id, name FROM heroes WHERE name = ?1",
        [name],
        |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
    )
    .map_err(|_| anyhow::anyhow!("Hero '{}' not found", name))
}

fn skill_file_path(hero_name: &str, skill_name: &str) -> std::path::PathBuf {
    db::guild_dir()
        .join("workspace/memory/heroes")
        .join(hero_name)
        .join("skills")
        .join(format!("{}.md", skill_name))
}

fn run_list(hero: String) -> Result<()> {
    let conn = db::open()?;
    let (hero_id, hero_name) = resolve_hero(&conn, &hero)?;

    let mut stmt = conn.prepare(
        "SELECT name, type, proficiency FROM hero_skills WHERE hero_id = ?1 ORDER BY type, name"
    )?;
    let skills = stmt.query_map([&hero_id], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, i32>(2)?,
        ))
    })?;

    println!("{} {}", "SKILLS FOR".yellow().bold(), hero_name.cyan().bold());
    println!("{}", "─".repeat(50));

    let mut count = 0;
    for skill in skills {
        let (name, stype, prof) = skill?;
        let stars = "★".repeat(prof as usize) + &"☆".repeat((5 - prof).max(0) as usize);
        println!("  {} {} [{}]", name.bold(), stars, stype.dimmed());
        count += 1;
    }

    if count == 0 {
        println!("  No skills found. Use {} to add one.", "guild skill add".cyan());
    }

    Ok(())
}

fn run_show(hero: String, skill: String) -> Result<()> {
    let conn = db::open()?;
    let (hero_id, hero_name) = resolve_hero(&conn, &hero)?;

    let row = conn.query_row(
        "SELECT name, type, proficiency, source, created_at, updated_at FROM hero_skills WHERE hero_id = ?1 AND name = ?2",
        rusqlite::params![hero_id, skill],
        |row| Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, i32>(2)?,
            row.get::<_, Option<String>>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, String>(5)?,
        )),
    );

    match row {
        Ok((name, stype, prof, source, created_at, updated_at)) => {
            let stars = "★".repeat(prof as usize) + &"☆".repeat((5 - prof).max(0) as usize);
            println!("{} {} — {}", "Skill:".yellow(), name.bold(), hero_name.cyan());
            println!("  Type:        {}", stype);
            println!("  Proficiency: {}", stars);
            if let Some(src) = source {
                println!("  Source:      {}", src);
            }
            println!("  Created:     {}", created_at.dimmed());
            println!("  Updated:     {}", updated_at.dimmed());

            // Read backing file if it exists
            let file_path = skill_file_path(&hero_name, &name);
            if file_path.exists() {
                let content = std::fs::read_to_string(&file_path)?;
                println!();
                println!("{}", "─".repeat(50));
                println!("{}", content);
            }
        }
        Err(_) => bail!("Skill '{}' not found for hero '{}'", skill, hero_name),
    }

    Ok(())
}

fn run_add(hero: String, skill: String) -> Result<()> {
    let conn = db::open()?;
    let (hero_id, hero_name) = resolve_hero(&conn, &hero)?;

    // Check if skill already exists
    let exists: bool = conn
        .query_row(
            "SELECT COUNT(*) FROM hero_skills WHERE hero_id = ?1 AND name = ?2",
            rusqlite::params![hero_id, skill],
            |row| row.get::<_, i32>(0),
        )
        .map(|c| c > 0)
        .unwrap_or(false);

    if exists {
        bail!("Hero '{}' already has skill '{}'", hero_name, skill);
    }

    let now = Utc::now().to_rfc3339();
    let skill_id = uuid::Uuid::new_v4().to_string();

    conn.execute(
        "INSERT INTO hero_skills (id, hero_id, name, type, proficiency, source, created_at, updated_at) VALUES (?1, ?2, ?3, 'manual', 1, NULL, ?4, ?5)",
        rusqlite::params![skill_id, hero_id, skill, now, now],
    )?;

    // Create backing file
    let file_path = skill_file_path(&hero_name, &skill);
    if let Some(parent) = file_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&file_path, format!("# {}\n\nManually added skill.\n", skill))?;

    db::log_activity(
        &conn,
        "system",
        &format!("Skill '{}' added to hero '{}'", skill, hero_name),
        None,
        None,
        "info",
    )?;

    println!("{} Skill '{}' added to hero '{}'", "✓".green(), skill.bold(), hero_name.cyan());
    println!("  Backing file: {}", file_path.display().to_string().dimmed());

    Ok(())
}

fn run_remove(hero: String, skill: String) -> Result<()> {
    let conn = db::open()?;
    let (hero_id, hero_name) = resolve_hero(&conn, &hero)?;

    let deleted = conn.execute(
        "DELETE FROM hero_skills WHERE hero_id = ?1 AND name = ?2",
        rusqlite::params![hero_id, skill],
    )?;

    if deleted == 0 {
        bail!("Skill '{}' not found for hero '{}'", skill, hero_name);
    }

    // Optionally delete backing file
    let file_path = skill_file_path(&hero_name, &skill);
    if file_path.exists() {
        let confirm = dialoguer::Confirm::new()
            .with_prompt(format!("Delete backing file {}?", file_path.display()))
            .default(false)
            .interact()?;

        if confirm {
            std::fs::remove_file(&file_path)?;
            println!("  Backing file deleted.");
        }
    }

    db::log_activity(
        &conn,
        "system",
        &format!("Skill '{}' removed from hero '{}'", skill, hero_name),
        None,
        None,
        "info",
    )?;

    println!("{} Skill '{}' removed from hero '{}'", "✓".green(), skill.bold(), hero_name.cyan());

    Ok(())
}

fn run_edit(hero: String, skill: String) -> Result<()> {
    let guild_dir = db::guild_dir();
    let skill_path = guild_dir
        .join("workspace/memory/heroes")
        .join(&hero)
        .join("skills")
        .join(format!("{}.md", skill));

    if !skill_path.exists() {
        bail!("Skill file not found: {}", skill_path.display());
    }

    let editor = std::env::var("EDITOR").unwrap_or_else(|_| "vi".to_string());
    std::process::Command::new(&editor)
        .arg(&skill_path)
        .status()?;

    println!(
        "{} Skill '{}' updated for hero '{}'",
        "✓".green(),
        skill.cyan(),
        hero
    );
    Ok(())
}

fn run_transfer(from_hero: String, to_hero: String, skill: String) -> Result<()> {
    let conn = db::open()?;
    let (from_id, from_name) = resolve_hero(&conn, &from_hero)?;
    let (to_id, to_name) = resolve_hero(&conn, &to_hero)?;

    // Fetch source skill
    let row = conn.query_row(
        "SELECT name, type, proficiency, source FROM hero_skills WHERE hero_id = ?1 AND name = ?2",
        rusqlite::params![from_id, skill],
        |row| Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, i32>(2)?,
            row.get::<_, Option<String>>(3)?,
        )),
    );

    let (skill_name, stype, prof, source) = match row {
        Ok(r) => r,
        Err(_) => bail!("Skill '{}' not found for hero '{}'", skill, from_name),
    };

    // Check if target already has the skill
    let exists: bool = conn
        .query_row(
            "SELECT COUNT(*) FROM hero_skills WHERE hero_id = ?1 AND name = ?2",
            rusqlite::params![to_id, skill_name],
            |row| row.get::<_, i32>(0),
        )
        .map(|c| c > 0)
        .unwrap_or(false);

    if exists {
        bail!("Hero '{}' already has skill '{}'", to_name, skill_name);
    }

    // Insert into target hero
    let now = Utc::now().to_rfc3339();
    let new_id = uuid::Uuid::new_v4().to_string();

    conn.execute(
        "INSERT INTO hero_skills (id, hero_id, name, type, proficiency, source, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
        rusqlite::params![new_id, to_id, skill_name, stype, prof, source, now, now],
    )?;

    // Copy backing file if it exists
    let src_path = skill_file_path(&from_name, &skill_name);
    let dst_path = skill_file_path(&to_name, &skill_name);

    if src_path.exists() {
        if let Some(parent) = dst_path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::copy(&src_path, &dst_path)?;
        println!("  Backing file copied to: {}", dst_path.display().to_string().dimmed());
    }

    db::log_activity(
        &conn,
        "system",
        &format!("Skill '{}' transferred from '{}' to '{}'", skill_name, from_name, to_name),
        None,
        None,
        "info",
    )?;

    println!(
        "{} Skill '{}' transferred from {} to {}",
        "✓".green(),
        skill_name.bold(),
        from_name.cyan(),
        to_name.cyan()
    );

    Ok(())
}
