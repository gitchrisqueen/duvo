# Eight verbs. Everything else lives in scripts/ so that both a human and an
# agent run exactly the same commands, and neither has to reconstruct them.

.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help setup dev test lint sec up down verify ship clock

help: ## Show the available commands
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies and git hooks (run once, before the session)
	@scripts/bootstrap.sh

dev: ## Run the server locally against the composed mock upstream
	@scripts/dev.sh

test: ## Fast unit suite. Must stay under five seconds.
	@scripts/test.sh

lint: ## Format, lint, typecheck, and check documentation prose
	@scripts/lint.sh

sec: ## Secret scan, SAST, and dependency audit
	@scripts/security.sh

up: ## Build and start the full stack
	@scripts/compose_up.sh

down: ## Stop the stack and remove volumes
	@scripts/compose_down.sh

verify: ## Everything: lint, test, security, build, stack, smoke, documented commands
	@scripts/verify_all.sh

ship: ## Verify, commit, push with retry, and open a draft pull request
	@scripts/pr.sh

clock: ## Start the interview timer in this terminal
	@scripts/timer.sh
