SHELL := /bin/bash
export PATH := $(HOME)/.cargo/bin:$(HOME)/.nvm/versions/node/$(shell ls $(HOME)/.nvm/versions/node/ 2>/dev/null | tail -1)/bin:$(PATH)

.PHONY: help build build-release build-fe dev dev-fe dev-api dev-all test test-rust test-python lint clean init install gm gm-stop

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

dev-all: ## Run API + frontend + Guild Master (all-in-one)
	@echo "Starting API(:7432) + Frontend(:5173) + Guild Master..."
	@trap 'kill 0' INT; \
		cargo run -- dashboard & \
		cd dashboard && npm run dev & \
		cd agents && python3 guild_master.py & \
		wait

# === Guild Master ===

gm: ## Start Guild Master (requires ANTHROPIC_API_KEY)
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "\033[31mError: ANTHROPIC_API_KEY not set\033[0m"; \
		echo "Run: export ANTHROPIC_API_KEY=sk-ant-..."; \
		exit 1; \
	fi
	cd agents && python3 guild_master.py

gm-stop: ## Stop Guild Master
	@if [ -f ~/.guild/guild-master.pid ]; then \
		kill $$(cat ~/.guild/guild-master.pid) 2>/dev/null && echo "Guild Master stopped" || echo "Guild Master not running"; \
		rm -f ~/.guild/guild-master.pid; \
	else \
		echo "No PID file found"; \
	fi

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
