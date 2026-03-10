.PHONY: test test-frontend up down build migrate logs

# Run backend tests using the test stage (rebuild only needed if dependencies change)
test:
	docker compose --env-file deploy/.env run --rm -T --build backend-test

# Run frontend tests locally
test-frontend:
	cd frontend && npx vitest run

# Start all services
up:
	docker compose --env-file deploy/.env up -d

# Stop all services
down:
	docker compose --env-file deploy/.env down

# Rebuild and start all services
build:
	docker compose --env-file deploy/.env up -d --build

# Run database migrations (uses 'run' so it works even if backend is stopped)
migrate:
	docker compose --env-file deploy/.env run --rm -T backend alembic upgrade head

# Tail logs
logs:
	docker compose --env-file deploy/.env logs -f
