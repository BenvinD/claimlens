.PHONY: help install check test lint format fmt dryrun verify validate run evaluate clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Sync the environment (package + dev tools)
	uv sync

check: lint format test dryrun verify  ## Run every offline check (no API spend)

test:  ## Run the test suite
	uv run pytest

lint:  ## Lint
	uv run ruff check .

format:  ## Check formatting
	uv run ruff format --check .

fmt:  ## Apply formatting
	uv run ruff format .

dryrun:  ## Offline check of the model-call wiring
	uv run claimlens dryrun --set sample

verify:  ## Validate output.csv against the data contract
	uv run claimlens verify

validate:  ## Score the rule layer on cached observations (no spend)
	uv run claimlens validate

run:  ## Full pipeline on the test set (COSTS MONEY)
	uv run claimlens run --set test

evaluate:  ## Compare models and rewrite the evaluation report (COSTS MONEY)
	uv run claimlens evaluate

clean:  ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache build dist
	find . -name __pycache__ -type d -not -path './.venv/*' -prune -exec rm -rf {} +
