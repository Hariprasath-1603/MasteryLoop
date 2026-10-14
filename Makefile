.PHONY: help up down ps logs migrate seed etl test clean

help:
	@echo "MasteryLoop M1 Development Commands:"
	@echo "  make up       - Start Postgres 16, Redis 7, Qdrant, MLflow"
	@echo "  make down     - Stop all infrastructure containers"
	@echo "  make ps       - List running containers and health status"
	@echo "  make logs     - View tail logs of infrastructure services"
	@echo "  make migrate  - Run Alembic database migrations to head"
	@echo "  make seed     - Populate PostgreSQL with idempotent seed graph & items"
	@echo "  make etl      - Run EdNet/ASSISTments chunked ETL and learner splits"
	@echo "  make test     - Run pytest test suite"
	@echo "  make clean    - Remove build artifacts, pycache, and temporary files"

up:
	docker compose up -d

down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs -f

migrate:
	alembic -c libs/common/src/masteryloop_common/db/migrations/alembic.ini upgrade head

seed:
	python -m masteryloop_common.db.seed

etl:
	uv run python -m masteryloop_ml.data.prepare_ednet --input-path data/raw --output-dir data/processed
	uv run python -m masteryloop_ml.data.splits --input-path data/processed/interactions.parquet --output-dir data/splits

test:
	uv run pytest tests -v
