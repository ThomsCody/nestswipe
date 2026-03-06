# Nestswipe — CLAUDE.md

## Sensitive data

**NEVER commit sensitive data.** This includes:
- `.env` files (any path — root, `deploy/`, `backend/`)
- `oauth.json` files
- API keys, passwords, tokens, secrets of any kind
- `deploy/setup-secrets.sh`
- Terraform state files (`*.tfstate`, `*.tfvars`)

All of these are in `.gitignore`. If you add new secrets, add them to `.gitignore` first.

## Project overview

Nestswipe is a real estate listing aggregator. It polls Gmail for listing alert emails (seloger.com, pap.fr, consultantsimmobilier.com), scrapes the listing pages, extracts structured data via GPT-4o-mini, and presents them in a Tinder-style swipe UI. Liked listings go to shared household favorites with comments and price tracking.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI (async), SQLAlchemy 2.0 (async), Alembic |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, @tanstack/react-query |
| Database | PostgreSQL 16 (asyncpg) |
| Object storage | MinIO (S3-compatible) |
| Scraping | curl_cffi (Chrome TLS impersonation), BeautifulSoup4 |
| Proxy | Decodo rotating residential proxy (seloger.com only, optional) |
| LLM | OpenAI GPT-4o-mini (extraction + photo classification) |
| Auth | Google OAuth 2.0 + JWT |
| Email | Gmail API + APScheduler |
| Monitoring | Datadog (ddtrace APM, RUM, logs) |
| CI | GitHub Actions (pytest) |

## Project structure

```
backend/
  app/
    api/          # FastAPI route handlers (auth, listings, favorites, household, etc.)
    models/       # SQLAlchemy models (user, listing, interaction)
    services/     # Business logic
      browser_scraper.py   # curl_cffi scraper with proxy support
      email_processor.py   # Main pipeline: email → scrape → LLM → store
      photo_storage.py     # Photo download + MinIO upload (httpx, no proxy)
      photo_scraper.py     # Extract photo URLs from email HTML
      photo_classifier.py  # GPT-4o-mini photo filtering
      llm_extractor.py     # GPT-4o-mini structured data extraction
      email_url_extractor.py # GPT-4o-mini URL identification
      duplicate_detector.py  # 4-layer dedup
    config.py     # Pydantic settings (env vars)
    database.py   # Async SQLAlchemy engine + session
    scheduler.py  # APScheduler email polling
    main.py       # FastAPI app with ddtrace
  alembic/        # DB migrations (sequential: 001_ through 008_)
  scripts/        # Maintenance scripts (backfill_listings.py)
  tests/          # pytest suite
frontend/
  src/            # React app
deploy/
  docker-compose.prod.yml  # Production stack (Caddy, Postgres, MinIO, Backend, DD Agent)
  deploy.sh                # Rsync + remote deploy
  remote-deploy.sh         # Runs on the server (build, migrate, up)
  Caddyfile                # Reverse proxy config
  .env                     # Production secrets (NEVER committed)
docker-compose.yml         # Local dev stack
```

## Running locally

```bash
# All services via Docker (Colima or Docker Desktop)
docker compose --env-file deploy/.env up -d

# Run migrations
docker compose exec backend alembic upgrade head
```

The `--env-file deploy/.env` flag is required — the compose file references env vars that live in `deploy/.env`.

Frontend: http://localhost:5173 | Backend API: http://localhost:8000 | MinIO console: http://localhost:9001

## Production deployment

```bash
./deploy/deploy.sh
```

Rsync's code to the production server, builds containers, runs migrations, and starts services. Secrets (`deploy/.env`, `deploy/oauth.json`) must exist on the server already — they are excluded from rsync.

## Database

- Async PostgreSQL via asyncpg + SQLAlchemy 2.0 async sessions
- Migrations are sequential Alembic files: `backend/alembic/versions/001_` through `008_`
- Create new migrations: `docker compose exec backend alembic revision -m "description"`
- Apply migrations: `docker compose exec backend alembic upgrade head`

## Key patterns

- **Async everywhere** — all DB, HTTP, and service calls are async/await
- **Dependency injection** — `get_db()` yields async sessions via FastAPI `Depends`
- **Proxy is conditional** — `browser_scraper.py` only uses proxy for sources in `PROXY_SOURCES` (currently just `seloger`). Photo downloads in `photo_storage.py` (httpx) never use the proxy.
- **Warm-up requests** — scraper visits the homepage before listing URLs to establish cookies
- **Email pipeline** — scheduler → poll Gmail → extract URLs (LLM) → scrape pages (curl_cffi) → extract data (LLM) → download/classify photos (LLM) → dedup → store
- **4-layer dedup** — source_id, URL, content fingerprint (SHA256), perceptual image hash (phash)

## Testing

```bash
cd backend
pytest -v
```

63 tests with mocked external services. CI runs on every push/PR to `main`.

## Environment variables

All set in `deploy/.env`. Key variables:
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — database credentials
- `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` — object storage
- `JWT_SECRET` — JWT signing key (generate with `openssl rand -hex 32`)
- `PROXY_HOST`, `PROXY_USER`, `PROXY_PASSWORD` — optional residential proxy for seloger.com
- `DD_API_KEY` — Datadog agent (production only)

Google OAuth credentials are loaded from `oauth.json` (not env vars).
OpenAI API keys are set per-user in the app settings UI.
