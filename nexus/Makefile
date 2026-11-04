.PHONY: setup migrate seed start stop logs reset health demo-mode help

setup:
	pip install -r requirements.txt
	python artisan.py migrate
	python artisan.py agents:setup

migrate:
	python artisan.py migrate

seed:
	python artisan.py seed

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
	python artisan.py migrate
	python artisan.py seed

health:
	python artisan.py health:check

demo-mode:
	ESCALATION_CHECK_MINUTES=5 GEO_SEO_INTERVAL_HOURS=1 docker compose up -d

help:
	@echo "make setup      — install deps, run migrations, register Switch agents"
	@echo "make migrate    — run database migrations"
	@echo "make seed       — load demo data"
	@echo "make start      — start all services"
	@echo "make stop       — stop all services"
	@echo "make health     — run system health check"
	@echo "make demo-mode  — start with short intervals for demo"
