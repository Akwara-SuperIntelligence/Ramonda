.PHONY: up down reset check

up:
	docker compose up -d --wait

down:
	docker compose down

reset:
	docker compose down -v

check:
	python3 scripts/check_links.py
