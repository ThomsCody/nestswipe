# Nestswipe

A web app to find your next apartment. Reads housing offer emails from Gmail (seloger.com, pap.fr, consultantsimmobilier.com), extracts structured listing data using an LLM, and presents listings in a Tinder-style swipe UI. Liked listings go to a shared favorites section where household members can comment and track price changes.

## Features

- **Email ingestion** — Polls Gmail every 5 minutes for listing alert emails, extracts candidate URLs via GPT-4o-mini
- **Smart scraping** — Follows tracking URLs with Chrome TLS fingerprint impersonation (curl_cffi), extracts page content
- **LLM extraction** — Extracts structured data (price, sqm, bedrooms, city, district, etc.) from listing pages using GPT-4o-mini
- **Photo classification** — Filters out agent portraits, logos, maps, and floor plans using GPT-4o-mini vision
- **Duplicate detection** — 4-layer dedup: source ID, URL, content fingerprint (SHA256), perceptual image hashing (phash)
- **Swipe UI** — Tinder-style card swiping to like/pass on listings
- **Shared favorites** — Household members see the same favorites, can comment and track price history
- **Household invites** — Invite another user by email to join your household

## Prerequisites

- **Docker + Docker Compose** (or [Colima](https://github.com/abiosoft/colima) as a Docker Desktop alternative)
- **Google Cloud Console** project with:
  - Gmail API enabled
  - OAuth 2.0 credentials (Web application type)
  - Redirect URI: `http://localhost:8000/api/v1/auth/google/callback`
  - Scopes: `openid`, `email`, `profile`, `gmail.readonly`
- **OpenAI API key** (each user configures their own in the app)

## Setup

1. **Clone and configure**

   ```bash
   git clone <repo-url> && cd nestswipe
   ```

2. **Google OAuth credentials**

   Download your OAuth credentials from Google Cloud Console and save as `oauth.json` in the project root:

   ```json
   {
     "web": {
       "client_id": "YOUR_CLIENT_ID",
       "client_secret": "YOUR_CLIENT_SECRET",
       "redirect_uris": ["http://localhost:8000/api/v1/auth/google/callback"],
       "auth_uri": "https://accounts.google.com/o/oauth2/auth",
       "token_uri": "https://oauth2.googleapis.com/token"
     }
   }
   ```

3. **Environment variables**

   ```bash
   cp deploy/.env.prod.example deploy/.env
   # Edit deploy/.env with real credentials
   ```

   The `deploy/.env` file is used by both local and production stacks. See `.env.example` for a description of all variables and their defaults.

## Running locally

```bash
docker compose --env-file deploy/.env up -d
```

This starts:
- **PostgreSQL** (`:5432`)
- **MinIO** (`:9000` API, `:9001` console)
- **Backend / FastAPI** (`:8000`)
- **Frontend / nginx** (`:5173`)

Run database migrations on first start (or after schema changes):

```bash
docker compose exec backend alembic upgrade head
```

Open [http://localhost:5173](http://localhost:5173) and sign in with Google. Then go to Settings and enter your OpenAI API key — the email processor will start polling your Gmail automatically every 5 minutes.

### Rebuilding after code changes

```bash
docker compose --env-file deploy/.env build && docker compose --env-file deploy/.env up -d
```

### Running without Docker

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend** (with hot reload):
```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to `localhost:8000`.

## Production deployment

Production runs on an Ubuntu server behind a Caddy reverse proxy with automatic HTTPS.

1. **First-time setup on the server:** create `deploy/.env` and `deploy/oauth.json` with production credentials (these files are excluded from rsync).

2. **Deploy from your machine:**

   ```bash
   ./deploy/deploy.sh
   ```

   This syncs the code to the server, builds containers, runs migrations, and starts all services.

The production stack (`deploy/docker-compose.prod.yml`) includes:
- **Caddy** — automatic HTTPS reverse proxy
- **PostgreSQL** — persistent data
- **MinIO** — photo storage
- **Backend** — FastAPI with ddtrace APM instrumentation
- **Frontend** — static build served by Caddy
- **Datadog Agent** — logs, APM traces, network performance monitoring

## Proxy configuration (optional)

Seloger.com uses Datadome bot protection which blocks direct scraping. A rotating residential proxy (e.g. [Decodo](https://decodo.com)) can be configured to bypass this. Set these in `deploy/.env`:

```
PROXY_HOST=gate.decodo.com:7777
PROXY_USER=your_username
PROXY_PASSWORD=your_password
```

When configured, the proxy is used **only** for HTML fetching on seloger.com — other sources (pap.fr, etc.) and photo downloads always use direct connections to save bandwidth.

If these variables are not set, the scraper falls back to direct connections (seloger may return blocks/CAPTCHAs).

## Architecture

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| State | @tanstack/react-query |
| Backend | Python 3.12 + FastAPI (async) |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 (async) + Alembic |
| Photos | MinIO (S3-compatible) |
| Scraping | curl_cffi (Chrome TLS impersonation) + BeautifulSoup |
| Proxy | Rotating residential proxy (Decodo) for Datadome bypass |
| Email | APScheduler + Gmail API |
| LLM | OpenAI GPT-4o-mini (extraction + photo classification) |
| Auth | Google OAuth 2.0 + JWT |
| Monitoring | Datadog (APM traces, log correlation, RUM, network monitoring) |
| CI | GitHub Actions (pytest on push/PR) |

## Testing

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-test.txt
pytest -v
```

63 tests covering API endpoints, service logic (duplicate detection, photo scraping), and the full email processing pipeline with mocked external services.

Tests run automatically on every push/PR to `main` via GitHub Actions.
