.PHONY: setup migrate seed start stop logs reset health demo demo-mode test help

setup:
	pip install -r requirements.txt
	python database/migrate_fresh.py
	python register_agents.py

migrate:
	python database/migrate_fresh.py

seed:
	python database/demo_slack_setup.py

start:
	docker compose up -d

stop:
	docker compose down

logs:
	docker compose logs -f

reset:
	docker compose down -v
	docker compose up postgres -d
	sleep 5
	python database/migrate_fresh.py

health:
	python artisan.py health:check

demo:
	@echo "==> Starting postgres..."
	docker compose up postgres -d
	@echo "==> Waiting for postgres to be ready..."
	sleep 5
	@echo "==> Running migrations + seed..."
	python database/migrate_fresh.py
	@echo "==> Launching all 7 agents (LLM_MOCK_MODE=true)..."
	LLM_MOCK_MODE=true python run_agents.py

test:
	python3 -m pytest tests/Unit/ -v

demo-mode:
	ESCALATION_CHECK_MINUTES=5 GEO_SEO_INTERVAL_HOURS=1 LLM_MOCK_MODE=true python run_agents.py

help:
	@echo "make demo       — one command: postgres up, migrate, launch all 7 agents (mock LLM)"
	@echo "make test       — run unit tests (pytest tests/Unit/)"
	@echo "make setup      — install deps, run migrations, register Switch agents"
	@echo "make migrate    — drop + recreate all tables"
	@echo "make seed       — post demo cards to Slack channels"
	@echo "make start      — start all services via docker compose"
	@echo "make stop       — stop all services"
	@echo "make health     — run system health check"
	@echo "make demo-mode  — run agents with short intervals + mock LLM (no docker)"
