use anyhow::Result;
use clap::Subcommand;
use colored::Colorize;
use serde_json::Value;
use std::fs;

use crate::db;

#[derive(Subcommand)]
pub enum ConfigCommand {
    /// Show current configuration
    Show,
    /// Set a config value
    Set {
        /// Config key (e.g. cost-cap-daily, daily-briefing-time)
        key: String,
        /// Config value
        value: String,
    },
    /// Skip rookie period
    SkipRookie,
}

fn config_path() -> std::path::PathBuf {
    db::guild_dir().join("config.json")
}

fn load_config() -> Result<Value> {
    let path = config_path();
    if path.exists() {
        let content = fs::read_to_string(&path)?;
        Ok(serde_json::from_str(&content).unwrap_or(Value::Object(serde_json::Map::new())))
    } else {
        Ok(Value::Object(serde_json::Map::new()))
    }
}

fn save_config(config: &Value) -> Result<()> {
    let path = config_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&path, serde_json::to_string_pretty(config)?)?;
    Ok(())
}

pub fn run(cmd: ConfigCommand) -> Result<()> {
    match cmd {
        ConfigCommand::Show => run_show(),
        ConfigCommand::Set { key, value } => run_set(key, value),
        ConfigCommand::SkipRookie => run_skip_rookie(),
    }
}

fn run_show() -> Result<()> {
    let config = load_config()?;

    println!("{}", "GUILD CONFIGURATION".yellow().bold());
    println!("{}", "─".repeat(50));

    let obj = config.as_object().unwrap();
    if obj.is_empty() {
        println!("  No configuration values set.");
        println!("  Use {} to set a value.", "guild config set <key> <value>".cyan());
    } else {
        for (key, value) in obj {
            match value {
                Value::Object(map) => {
                    println!("  {}:", key.cyan());
                    for (k, v) in map {
                        println!("    {}: {}", k, format_value(v));
                    }
                }
                _ => {
                    println!("  {}: {}", key.cyan(), format_value(value));
                }
            }
        }
    }

    println!();
    println!("Config file: {}", config_path().display().to_string().dimmed());

    Ok(())
}

fn run_set(key: String, value: String) -> Result<()> {
    // Keys that are stored in the DB config table
    let db_keys = ["cost-cap-daily"];

    if db_keys.contains(&key.as_str()) {
        let conn = db::open()?;
        db::set_config(&conn, &key, &value)?;
        println!("{} Config '{}' set to '{}'", "+".green(), key.cyan(), value);
        return Ok(());
    }

    let mut config = load_config()?;

    // Try to parse value as number or bool, fall back to string
    let parsed: Value = if value == "true" {
        Value::Bool(true)
    } else if value == "false" {
        Value::Bool(false)
    } else if let Ok(n) = value.parse::<i64>() {
        Value::Number(n.into())
    } else if let Ok(n) = value.parse::<f64>() {
        serde_json::Number::from_f64(n)
            .map(Value::Number)
            .unwrap_or(Value::String(value.clone()))
    } else {
        Value::String(value.clone())
    };

    config
        .as_object_mut()
        .expect("config must be an object")
        .insert(key.clone(), parsed);

    save_config(&config)?;

    println!("{} Config '{}' set to '{}'", "+".green(), key.cyan(), value);

    Ok(())
}

fn run_skip_rookie() -> Result<()> {
    let mut config = load_config()?;

    config
        .as_object_mut()
        .expect("config must be an object")
        .insert("rookie_mode".to_string(), Value::Bool(false));

    save_config(&config)?;

    println!("{} Rookie mode disabled.", "+".green());
    println!("  Verbose explanations will no longer be shown.");

    Ok(())
}

fn format_value(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Number(n) => n.to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Null => "null".to_string(),
        other => other.to_string(),
    }
}
