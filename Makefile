.DEFAULT_GOAL := help

.PHONY: help install lint format check test build run clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	uv sync

lint: ## Run ruff linter
	uv run ruff check src/ tests/

format: ## Format code with ruff
	uv run ruff format src/ tests/

check: lint ## Lint + verify formatting
	uv run ruff format --check src/ tests/

test: ## Run tests
	uv run pytest tests/ -v

build: ## Build package
	uv build

run: ## Start the MCP server
	uv run pulumi-events

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .pytest_cache
	find src/ tests/ -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
