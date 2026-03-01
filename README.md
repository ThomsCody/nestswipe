# Nestswipe

A web app to find your next apartment. Reads housing offer emails from Gmail (seloger.com, pap.fr), extracts structured listing data using an LLM, and presents listings in a Tinder-style swipe UI. Liked listings go to a shared favorites section where both household members can comment and track price changes.

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

   Navigate to Settings and enter your OpenAI API key. The email processor will start polling your Gmail automatically every 15 minutes.

## Architecture

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| State | @tanstack/react-query |
| Backend | Python 3.12 + FastAPI (async) |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 (async) + Alembic |
| Photos | MinIO (S3-compatible) |
| Email | APScheduler + Gmail API |
| LLM | OpenAI gpt-4o-mini |
| Auth | Google OAuth 2.0 + JWT |

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

## Rebuilding

```bash
docker compose build && docker compose up -d
```
