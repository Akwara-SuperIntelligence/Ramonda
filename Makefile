.PHONY: up down reset migrate test

up:
	docker compose up -d --wait

down:
	docker compose down

reset:
	docker compose down -v

migrate:
	cat services/agent/migrations/*.sql | docker compose exec -T postgres psql -q -U ramonda -d agent

test: migrate
	cd services/agent && ../../.venv/bin/python -m pytest
