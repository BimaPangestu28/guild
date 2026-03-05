use anyhow::Result;

#[derive(Debug, Clone, PartialEq)]
pub enum Tier {
    Free,
    Pro,
}

pub struct License {
    pub tier: Tier,
    pub max_heroes: usize,
}

impl License {
    pub fn load() -> Self {
        let guild_dir = crate::db::guild_dir();
        let license_path = guild_dir.join("license.key");

        if let Ok(key) = std::fs::read_to_string(&license_path) {
            if verify_key(key.trim()) {
                return License { tier: Tier::Pro, max_heroes: 8 };
            }
        }

        License { tier: Tier::Free, max_heroes: 2 }
    }

    pub fn check_hero_limit(&self) -> Result<()> {
        let conn = crate::db::open()?;
        let count: i32 = conn.query_row("SELECT COUNT(*) FROM heroes", [], |r| r.get(0))?;
        if count as usize >= self.max_heroes {
            anyhow::bail!(
                "Hero limit reached ({}/{}). {} to add more.",
                count, self.max_heroes,
                if self.tier == Tier::Free { "Upgrade to Pro" } else { "Max heroes reached" }
            );
        }
        Ok(())
    }
}

/// Simple key verification: key format is "GUILD-PRO-{hash}"
/// Hash = first 8 chars of hex(sha256("guild-pro-" + machine_id))
fn verify_key(key: &str) -> bool {
    if !key.starts_with("GUILD-PRO-") {
        return false;
    }
    // For now, accept any key starting with GUILD-PRO-
    // Real implementation would verify against machine ID
    true
}

pub fn activate(key: &str) -> Result<()> {
    if !verify_key(key) {
        anyhow::bail!("Invalid license key");
    }
    let guild_dir = crate::db::guild_dir();
    std::fs::write(guild_dir.join("license.key"), key)?;
    Ok(())
}
