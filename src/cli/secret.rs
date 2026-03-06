use anyhow::{bail, Result};
use clap::Subcommand;
use colored::Colorize;
use serde_json::{Map, Value};
use std::fs;
use std::path::PathBuf;

use crate::db;

#[derive(Subcommand)]
pub enum SecretCommand {
    /// Add or update a secret
    Add { name: String, value: String },
    /// List secret names (never values)
    List,
    /// Remove a secret
    Remove { name: String },
}

pub fn run(cmd: SecretCommand) -> Result<()> {
    match cmd {
        SecretCommand::Add { name, value } => run_add(name, value),
        SecretCommand::List => run_list(),
        SecretCommand::Remove { name } => run_remove(name),
    }
}

fn secrets_path() -> PathBuf {
    db::guild_dir().join("secrets.json")
}

/// Derive an obfuscation key from the machine's hostname + home directory path.
fn get_key() -> Vec<u8> {
    // Read hostname from /etc/hostname (Linux) or fall back to a default
    let hostname = fs::read_to_string("/etc/hostname")
        .map(|s| s.trim().to_string())
        .unwrap_or_else(|_| "guild-default-host".to_string());

    let home = dirs::home_dir()
        .map(|p| p.display().to_string())
        .unwrap_or_else(|| "/home/unknown".to_string());

    let combined = format!("guild-secret-{}:{}", hostname, home);
    combined.into_bytes()
}

/// XOR data against a repeating key.
fn xor_bytes(data: &[u8], key: &[u8]) -> Vec<u8> {
    data.iter()
        .enumerate()
        .map(|(i, b)| b ^ key[i % key.len()])
        .collect()
}

// ---------- Simple base64 encode/decode (no external crate) ----------

const B64_CHARS: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

fn b64_encode(data: &[u8]) -> String {
    let mut out = String::new();
    let chunks = data.chunks(3);
    for chunk in chunks {
        let b0 = chunk[0] as u32;
        let b1 = if chunk.len() > 1 { chunk[1] as u32 } else { 0 };
        let b2 = if chunk.len() > 2 { chunk[2] as u32 } else { 0 };
        let triple = (b0 << 16) | (b1 << 8) | b2;

        out.push(B64_CHARS[((triple >> 18) & 0x3F) as usize] as char);
        out.push(B64_CHARS[((triple >> 12) & 0x3F) as usize] as char);

        if chunk.len() > 1 {
            out.push(B64_CHARS[((triple >> 6) & 0x3F) as usize] as char);
        } else {
            out.push('=');
        }

        if chunk.len() > 2 {
            out.push(B64_CHARS[(triple & 0x3F) as usize] as char);
        } else {
            out.push('=');
        }
    }
    out
}

fn b64_decode(s: &str) -> Result<Vec<u8>> {
    fn b64_val(c: u8) -> Result<u8> {
        match c {
            b'A'..=b'Z' => Ok(c - b'A'),
            b'a'..=b'z' => Ok(c - b'a' + 26),
            b'0'..=b'9' => Ok(c - b'0' + 52),
            b'+' => Ok(62),
            b'/' => Ok(63),
            _ => bail!("Invalid base64 character: {}", c as char),
        }
    }

    let bytes: Vec<u8> = s.bytes().filter(|&b| b != b'=').collect();
    let mut out = Vec::new();

    for chunk in bytes.chunks(4) {
        let len = chunk.len();
        if len < 2 {
            break;
        }
        let a = b64_val(chunk[0])? as u32;
        let b = b64_val(chunk[1])? as u32;
        let c = if len > 2 { b64_val(chunk[2])? as u32 } else { 0 };
        let d = if len > 3 { b64_val(chunk[3])? as u32 } else { 0 };

        let triple = (a << 18) | (b << 12) | (c << 6) | d;

        out.push(((triple >> 16) & 0xFF) as u8);
        if len > 2 {
            out.push(((triple >> 8) & 0xFF) as u8);
        }
        if len > 3 {
            out.push((triple & 0xFF) as u8);
        }
    }

    Ok(out)
}

// ---------- Encrypt / Decrypt ----------

fn encrypt(value: &str, key: &[u8]) -> String {
    let xored = xor_bytes(value.as_bytes(), key);
    b64_encode(&xored)
}

fn decrypt(encoded: &str, key: &[u8]) -> Result<String> {
    let decoded = b64_decode(encoded)?;
    let xored = xor_bytes(&decoded, key);
    String::from_utf8(xored).map_err(|e| anyhow::anyhow!("Failed to decrypt secret: {}", e))
}

// ---------- Secrets file I/O ----------

fn load_secrets() -> Result<Map<String, Value>> {
    let path = secrets_path();
    if !path.exists() {
        return Ok(Map::new());
    }
    let content = fs::read_to_string(&path)?;
    if content.trim().is_empty() {
        return Ok(Map::new());
    }
    let val: Value = serde_json::from_str(&content)?;
    match val {
        Value::Object(map) => Ok(map),
        _ => bail!("secrets.json is not a valid JSON object"),
    }
}

fn save_secrets(secrets: &Map<String, Value>) -> Result<()> {
    let path = secrets_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let content = serde_json::to_string_pretty(&Value::Object(secrets.clone()))?;
    fs::write(&path, content)?;
    Ok(())
}

// ---------- Command handlers ----------

pub fn run_add(name: String, value: String) -> Result<()> {
    let key = get_key();
    let encrypted = encrypt(&value, &key);

    let mut secrets = load_secrets()?;
    let is_update = secrets.contains_key(&name);
    secrets.insert(name.clone(), Value::String(encrypted));
    save_secrets(&secrets)?;

    if is_update {
        println!("{} Secret '{}' updated", "~".yellow(), name.bold());
    } else {
        println!("{} Secret '{}' added", "+".green(), name.bold());
    }

    Ok(())
}

fn run_list() -> Result<()> {
    let secrets = load_secrets()?;

    println!("{}", "SECRETS".yellow().bold());
    println!("{}", "-".repeat(40));

    if secrets.is_empty() {
        println!("  No secrets stored.");
        println!(
            "  Use {} to add one.",
            "guild secret add <name> <value>".cyan()
        );
    } else {
        for name in secrets.keys() {
            println!("  {} = {}", name.bold(), "****".dimmed());
        }
        println!("\n  {} secret(s) stored.", secrets.len());
    }

    Ok(())
}

fn run_remove(name: String) -> Result<()> {
    let mut secrets = load_secrets()?;

    if secrets.remove(&name).is_none() {
        bail!("Secret '{}' not found", name);
    }

    save_secrets(&secrets)?;

    println!("{} Secret '{}' removed", "-".red(), name.bold());

    Ok(())
}

/// Retrieve a decrypted secret value by name.
/// Intended for use by other modules (e.g., Telegram setup).
#[allow(dead_code)]
pub fn get_secret(name: &str) -> Result<Option<String>> {
    let secrets = load_secrets()?;
    match secrets.get(name) {
        Some(Value::String(encrypted)) => {
            let key = get_key();
            let decrypted = decrypt(encrypted, &key)?;
            Ok(Some(decrypted))
        }
        _ => Ok(None),
    }
}
