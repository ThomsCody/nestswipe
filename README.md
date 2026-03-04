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
   cp .env.example .env
   # Edit .env if needed (defaults work for local development)
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

3. **Start services**

   ```bash
   docker compose up -d
   ```

   This starts:
   - PostgreSQL (`:5432`)
   - MinIO (`:9000` API, `:9001` console)
   - Backend / FastAPI (`:8000`)
   - Frontend / nginx (`:5173`)

4. **Run database migrations**

   ```bash
   docker compose exec backend alembic upgrade head
   ```

5. **Open the app**

   Go to [http://localhost:5173](http://localhost:5173) and sign in with Google.

6. **Configure your OpenAI API key**

   Navigate to Settings and enter your OpenAI API key. The email processor will start polling your Gmail automatically every 5 minutes.

## Architecture

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| State | @tanstack/react-query |
| Backend | Python 3.12 + FastAPI (async) |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 (async) + Alembic |
| Photos | MinIO (S3-compatible) |
| Scraping | curl_cffi (Chrome TLS impersonation) + BeautifulSoup |
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

## Development

**Backend only** (for local dev without Docker):
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend only** (with hot reload):
```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to `localhost:8000`.

## Production Deployment

Production runs on an Ubuntu server behind Caddy reverse proxy at `nestswipe.duckdns.org`.

```bash
# Configure production env
cp deploy/.env.prod.example deploy/.env
# Edit deploy/.env with real credentials

# Deploy
./deploy/deploy.sh
```

The production stack (`deploy/docker-compose.prod.yml`) includes:
- **Caddy** — automatic HTTPS reverse proxy
- **PostgreSQL** — persistent data
- **MinIO** — photo storage
- **Backend** — FastAPI with ddtrace APM instrumentation
- **Frontend** — static build served by Caddy
- **Datadog Agent** — logs, APM traces, network performance monitoring

## Rebuilding

```bash
docker compose build && docker compose up -d
```
