.PHONY: setup start stop logs seed reset help demo-mode

setup:
	pip install -r requirements.txt
	python db_init.py
	python switch_setup.py

start:
	docker compose up -d

stop:
	docker compose down

logs:
	docker compose logs -f

seed:
	python scripts/seed_demo_data.py

reset:
	docker compose down -v
	docker compose up postgres -d
	sleep 5
	python db_init.py
	python scripts/seed_demo_data.py

demo-mode:
	ESCALATION_CHECK_MINUTES=5 GEO_SEO_INTERVAL_HOURS=1 docker compose up -d

help:
	@echo "make setup   — install deps, init DB, register Switch agents"
	@echo "make start   — start all services"
	@echo "make stop    — stop all services"
	@echo "make seed    — load demo data"
	@echo "make demo-mode — start with short intervals for demo"
