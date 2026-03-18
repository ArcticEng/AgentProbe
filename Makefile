.PHONY: dev api dashboard test test-unit test-prod test-billing admin deploy clean setup

PYTHON := python3
VENV := $(CURDIR)/.venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

setup: venv install  ## Full setup
venv:
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
install: venv  ## Install all deps
	$(PIP) install fastapi uvicorn stripe
	cd $(CURDIR)/dashboard && npm install

dev:  ## Start API + dashboard
	@make api &
	@sleep 2
	@make dashboard
api: venv  ## Start API server
	$(PY) -m uvicorn api.server:app --reload --port 8000
dashboard:  ## Start React dashboard
	cd $(CURDIR)/dashboard && npm run dev

test:  ## Quick demo (mock)
	$(PY) quickstart.py
test-unit:  ## Unit tests
	$(PY) tests/test_sdk.py
test-real:  ## Test real agent
	$(PY) test_real_agent.py
test-prod:  ## Production test + LLM-judge
	$(PY) test_production.py
test-billing:  ## Test billing flow (start API first)
	$(PY) test_billing.py

admin:  ## Admin dashboard (CLI)
	$(PY) admin.py
admin-customers:  ## List all customers
	$(PY) admin.py customers
admin-revenue:  ## Revenue summary
	$(PY) admin.py revenue
admin-usage:  ## Usage this month
	$(PY) admin.py usage
admin-runs:  ## Recent test runs
	$(PY) admin.py runs

stripe-setup:  ## Create Stripe products (run once)
	$(PY) billing/stripe_integration.py
build:  ## Build Docker image
	docker build -t agentprobe .
deploy:  ## Deploy to Fly.io
	fly deploy
clean:  ## Clean everything
	rm -rf dist/ build/ *.egg-info .venv dashboard/node_modules dashboard/dist __pycache__ results.json production_results.json billing/agentprobe.db
help:  ## Show all commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'
