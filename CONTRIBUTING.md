# Contributing to Guild

Thank you for your interest in contributing to Guild. This guide covers the essentials for getting started.

## Prerequisites

- **Rust** (1.75+) with `cargo`
- **Python** (3.10+)
- **Node.js** (18+) with `npm`
- **SQLite** (3.35+)

## Project Structure

```
src/            Rust CLI and core engine (Cargo project)
agents/         Python agent scripts (Guild Master, Hero Runtime, Memory Manager, etc.)
dashboard/      React + TypeScript web dashboard (Vite)
docs/           Design documents and specifications
```

## Setting Up

```bash
# Clone the repo
git clone <repo-url> && cd guild

# Rust
cargo build

# Python agents
cd agents
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt  # if present

# Dashboard
cd dashboard
npm install
npm run dev
```

## Running Tests

```bash
# Rust unit tests
cargo test

# Python tests
cd agents
python -m pytest test_memory_manager.py test_git_workflow.py -v
# or
python -m unittest discover -s agents -p 'test_*.py'
```

## Code Style

| Language   | Standard          | Tool                  |
|------------|-------------------|-----------------------|
| Rust       | rustfmt defaults  | `cargo fmt --check`   |
| Python     | PEP 8             | `ruff check` or `flake8` |
| TypeScript | ESLint config     | `npm run lint` in `dashboard/` |

Run formatters before committing:

```bash
cargo fmt
ruff format agents/    # or black agents/
```

## Commit Messages

Follow the Guild format:

```
[GLD-<quest-id>] <description> -- <hero-name>
```

Example: `[GLD-abc123] Add file lock conflict detection -- Merlin`

## Pull Request Process

1. Create a feature branch from `development`: `feature/GLD-<id>-<slug>`
2. Keep commits focused and well-described.
3. Ensure all tests pass (`cargo test` and Python tests).
4. Run linters/formatters.
5. Open a PR against `development` with a clear description.
6. Address review feedback promptly.

## Branch Naming

Branches follow the pattern: `<type>/GLD-<quest-id>-<slug>`

Types: `feature`, `bugfix`, `hotfix`, `chore`

## Reporting Issues

Open an issue with a clear title, steps to reproduce, expected vs. actual behavior, and relevant logs or screenshots.
