.PHONY: up down reset test

up:
	docker compose up -d --wait

down:
	docker compose down

reset:
	docker compose down -v

test:
	docker compose up -d --wait postgres
	cd services/agent && ../../.venv/bin/python -m pytest
