use anyhow::{bail, Result};
use chrono::Utc;
use colored::Colorize;

use crate::db;

const HERO_CLASSES: &[(&str, &[&str])] = &[
    ("Rust Sorcerer", &["rust", "wasm", "systems", "performance"]),
    ("Python Sage", &["python", "ml", "data", "scripting", "ai"]),
    ("Node Assassin", &["node", "typescript", "api", "realtime", "microservices"]),
    ("DevOps Paladin", &["devops", "kubernetes", "docker", "cicd", "azure", "infra"]),
    ("Frontend Archer", &["react", "typescript", "css", "ui"]),
    ("Data Shaman", &["sql", "etl", "databricks", "analytics", "data"]),
    ("ML Engineer", &["ml", "ai", "pytorch", "llm", "onnx", "python"]),
];

pub fn run_recruit(class: Option<String>, name: Option<String>) -> Result<()> {
    let conn = db::open()?;

    // Select class
    let (class_name, base_skills) = match class {
        Some(c) => {
            let found = HERO_CLASSES
                .iter()
                .find(|(name, _)| name.eq_ignore_ascii_case(&c));
            match found {
                Some((name, skills)) => (name.to_string(), skills.to_vec()),
                None => bail!("Unknown class '{}'. Available: {}", c,
                    HERO_CLASSES.iter().map(|(n, _)| *n).collect::<Vec<_>>().join(", ")),
            }
        }
        None => {
            let items: Vec<String> = HERO_CLASSES
                .iter()
                .map(|(name, skills)| format!("{} — {}", name, skills.join(", ")))
                .collect();
            let selection = dialoguer::Select::new()
                .with_prompt("Choose hero class")
                .items(&items)
                .default(0)
                .interact()?;
            let (name, skills) = HERO_CLASSES[selection];
            (name.to_string(), skills.to_vec())
        }
    };

    // Get name
    let hero_name = match name {
        Some(n) => n,
        None => dialoguer::Input::new()
            .with_prompt("Hero name")
            .interact_text()?,
    };

    let id = uuid::Uuid::new_v4().to_string();
    let now = Utc::now().to_rfc3339();

    conn.execute(
        "INSERT INTO heroes (id, name, class, status, level, xp, last_active) VALUES (?1, ?2, ?3, 'offline', 1, 0, ?4)",
        rusqlite::params![id, hero_name, class_name, now],
    )?;

    // Insert base skills
    for skill in &base_skills {
        let skill_id = uuid::Uuid::new_v4().to_string();
        conn.execute(
            "INSERT INTO hero_skills (id, hero_id, name, type, proficiency, source, created_at, updated_at) VALUES (?1, ?2, ?3, 'base', 1, NULL, ?4, ?5)",
            rusqlite::params![skill_id, id, skill, now, now],
        )?;
    }

    // Create hero memory directory
    let hero_dir = db::guild_dir()
        .join("workspace/memory/heroes")
        .join(&hero_name);
    std::fs::create_dir_all(hero_dir.join("skills"))?;
    std::fs::write(hero_dir.join("CLAUDE.md"), format!("# {} — {}\n", hero_name, class_name))?;
    std::fs::write(hero_dir.join("history.md"), "# Quest History\n")?;
    std::fs::write(hero_dir.join("notes.md"), "# Notes\n")?;

    db::log_activity(
        &conn,
        "system",
        &format!("Hero '{}' ({}) recruited", hero_name, class_name),
        None,
        None,
        "info",
    )?;

    println!("{} Hero {} ({}) recruited!", "✓".green(), hero_name.cyan().bold(), class_name);
    println!("  Skills: {}", base_skills.join(", "));
    println!();
    println!("Start this hero:");
    println!("  {}", format!("guild hero {} --start", hero_name).cyan());

    Ok(())
}

pub fn run_list() -> Result<()> {
    let conn = db::open()?;
    let mut stmt = conn.prepare(
        "SELECT name, class, status, level, xp, current_quest_id FROM heroes ORDER BY name"
    )?;
    let rows = stmt.query_map([], |row| {
        Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, i32>(3)?,
            row.get::<_, i32>(4)?,
            row.get::<_, Option<String>>(5)?,
        ))
    })?;

    println!("{}", "HERO ROSTER".yellow().bold());
    println!("{}", "─".repeat(60));

    let mut count = 0;
    for row in rows {
        let (name, class, status, level, xp, quest) = row?;
        let status_colored = match status.as_str() {
            "idle" => "IDLE".green(),
            "on_quest" => "ON QUEST".blue(),
            "resting" => "RESTING".yellow(),
            "blocked" => "BLOCKED".red(),
            "offline" => "OFFLINE".dimmed(),
            _ => status.normal(),
        };
        print!("  {} {} LV.{} [{}]", name.cyan().bold(), class.dimmed(), level, status_colored);
        if let Some(q) = quest {
            print!(" → {}", q);
        }
        println!(" ({} XP)", xp);
        count += 1;
    }

    if count == 0 {
        println!("  No heroes recruited. Use {} to recruit one.", "guild recruit".cyan());
    }

    Ok(())
}

pub fn run_show(name: String, start: bool) -> Result<()> {
    let conn = db::open()?;

    let hero = conn.query_row(
        "SELECT id, name, class, status, level, xp FROM heroes WHERE name = ?1",
        [&name],
        |row| Ok((
            row.get::<_, String>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, i32>(4)?,
            row.get::<_, i32>(5)?,
        ))
    );

    match hero {
        Ok((id, name, class, status, level, xp)) => {
            println!("{} {} — {}", "Hero:".yellow(), name.bold(), class);
            println!("  Status: {} | LV.{} | {} XP", status, level, xp);

            // Show skills
            let mut stmt = conn.prepare(
                "SELECT name, type, proficiency FROM hero_skills WHERE hero_id = ?1 ORDER BY type, name"
            )?;
            let skills = stmt.query_map([&id], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?, row.get::<_, i32>(2)?))
            })?;

            println!("  Skills:");
            for skill in skills {
                let (sname, stype, prof) = skill?;
                let stars = "★".repeat(prof as usize) + &"☆".repeat((5 - prof) as usize);
                println!("    {} {} [{}]", sname, stars, stype);
            }

            if start {
                println!();
                println!("Starting hero session...");
                println!("  {}", "(Session start will be implemented with Claude Code SDK integration)".dimmed());
            }
        }
        Err(_) => bail!("Hero '{}' not found", name),
    }

    Ok(())
}

pub fn run_retire(name: String) -> Result<()> {
    let conn = db::open()?;

    let confirm = dialoguer::Confirm::new()
        .with_prompt(format!("Retire hero '{}'?", name))
        .default(false)
        .interact()?;

    if !confirm {
        println!("Cancelled.");
        return Ok(());
    }

    let id: String = conn.query_row(
        "SELECT id FROM heroes WHERE name = ?1", [&name], |r| r.get(0)
    ).map_err(|_| anyhow::anyhow!("Hero '{}' not found", name))?;

    conn.execute("DELETE FROM hero_skills WHERE hero_id = ?1", [&id])?;
    conn.execute("DELETE FROM hero_mcps WHERE hero_id = ?1", [&id])?;
    conn.execute("DELETE FROM heroes WHERE id = ?1", [&id])?;

    println!("{} Hero '{}' retired", "✓".green(), name);
    Ok(())
}

pub fn run_pause(name: Option<String>, all: bool) -> Result<()> {
    let conn = db::open()?;
    if all {
        conn.execute("UPDATE heroes SET status = 'offline' WHERE status != 'offline'", [])?;
        println!("{} All heroes paused", "✓".green());
    } else if let Some(n) = name {
        let updated = conn.execute(
            "UPDATE heroes SET status = 'offline' WHERE name = ?1",
            [&n],
        )?;
        if updated == 0 { bail!("Hero '{}' not found", n); }
        println!("{} Hero '{}' paused", "✓".green(), n);
    } else {
        bail!("Specify a hero name or use --all");
    }
    Ok(())
}

pub fn run_resume(name: Option<String>, all: bool) -> Result<()> {
    let conn = db::open()?;
    if all {
        conn.execute("UPDATE heroes SET status = 'idle' WHERE status = 'offline'", [])?;
        println!("{} All heroes resumed", "✓".green());
    } else if let Some(n) = name {
        let updated = conn.execute(
            "UPDATE heroes SET status = 'idle' WHERE name = ?1 AND status = 'offline'",
            [&n],
        )?;
        if updated == 0 { bail!("Hero '{}' not found or not offline", n); }
        println!("{} Hero '{}' resumed", "✓".green(), n);
    } else {
        bail!("Specify a hero name or use --all");
    }
    Ok(())
}
