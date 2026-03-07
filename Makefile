SHELL := /bin/bash
export PATH := $(HOME)/.cargo/bin:$(HOME)/.nvm/versions/node/$(shell ls $(HOME)/.nvm/versions/node/ 2>/dev/null | tail -1)/bin:$(PATH)

.PHONY: help build build-release build-fe dev dev-fe dev-api test test-rust test-python lint clean init install

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# === Build ===

build: build-fe build-rust ## Build everything (frontend + Rust binary)

build-rust: ## Build Rust binary (debug)
	cargo build

build-release: build-fe ## Build optimized release binary with bundled dashboard
	cargo build --release

build-fe: ## Build frontend (dashboard)
	cd dashboard && npm install && npm run build

# === Development ===

dev: ## Run backend API + frontend dev server (parallel)
	@echo "Starting API server on :7432 and frontend dev on :5173..."
	@trap 'kill 0' INT; \
		cargo run -- dashboard & \
		cd dashboard && npm run dev & \
		wait

dev-api: ## Run only the API/dashboard server
	cargo run -- dashboard

dev-fe: ## Run only the frontend dev server (with API proxy)
	cd dashboard && npm run dev

# === Testing ===

test: test-rust test-python ## Run all tests

test-rust: ## Run Rust unit tests
	cargo test

test-python: ## Run Python unit tests
	cd agents && python3 -m unittest discover -v

# === Linting ===

lint: ## Lint everything
	cargo clippy 2>/dev/null || cargo check
	cd dashboard && npm run lint 2>/dev/null || true
	cd agents && python3 -m py_compile guild_master.py && \
		python3 -m py_compile hero_runtime.py && \
		python3 -m py_compile memory_manager.py && \
		python3 -m py_compile telegram_bot.py && \
		python3 -m py_compile git_workflow.py && \
		python3 -m py_compile mcp_builder.py && \
		echo "Python syntax OK"

# === CLI shortcuts ===

init: build-rust ## Init guild workspace
	./target/debug/guild init

doctor: build-rust ## Run health checks
	./target/debug/guild doctor

status: ## Show guild status (requires prior init)
	./target/debug/guild status

# === Cleanup ===

clean: ## Clean build artifacts
	cargo clean
	rm -rf dashboard/node_modules dashboard/dist

# === Install ===

install: build-release ## Install guild binary to ~/.cargo/bin
	cp target/release/guild ~/.cargo/bin/guild
	@echo "Installed to ~/.cargo/bin/guild"
