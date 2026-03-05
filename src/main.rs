mod api;
mod cli;
mod db;
mod license;
mod process_manager;

use anyhow::Result;
use clap::Parser;
use cli::Cli;

fn main() -> Result<()> {
    let cli = Cli::parse();
    cli::run(cli)
}
