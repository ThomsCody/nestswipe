.PHONY: test up down build migrate logs

# Run backend tests inside the container
test:
	docker compose --env-file deploy/.env exec -T backend python -m pytest tests/ -v --tb=short

# Start all services
up:
	docker compose --env-file deploy/.env up -d

# Stop all services
down:
	docker compose --env-file deploy/.env down

# Rebuild and start all services
build:
	docker compose --env-file deploy/.env up -d --build

# Run database migrations
migrate:
	docker compose --env-file deploy/.env exec backend alembic upgrade head

# Tail logs
logs:
	docker compose --env-file deploy/.env logs -f
