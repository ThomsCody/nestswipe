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
- **@mention notifications** — @mention a household member in a comment to send them an in-app notification and an email (via SendGrid)
- **Household invites** — Invite another user by email to join your household

## Prerequisites

- **Docker + Docker Compose** (or [Colima](https://github.com/abiosoft/colima) as a Docker Desktop alternative)
- **Google Cloud Console** project with:
  - Gmail API enabled
  - OAuth 2.0 credentials (Web application type)
  - Redirect URI: `http://localhost:8000/api/v1/auth/google/callback`
  - Scopes: `openid`, `email`, `profile`, `gmail.readonly`
- **OpenAI API key** (each user configures their own in the app)
- **SendGrid account** (optional — free tier gives 100 emails/day for @mention notifications)

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

### SeLoger JavaScript challenge fallback

A residential proxy alone cannot execute SeLoger's automatic device check. When
SeLoger scraping is challenged or has a transport error, the backend falls back
to the internal `seloger-browser` service. It runs full Chromium under a virtual
display, using the existing Decodo credentials with a stable French proxy session.
It waits for the JavaScript check and reload to finish before returning HTML.
Successful ordinary requests do not use the browser. No paid unblocking service,
personal browser cookies, or additional subscription is required.

Production Compose builds and starts this service and sets `SELOGER_BROWSER_URL`
for the backend. The service has no published port. It only accepts HTTPS URLs
on the supported SeLoger/Belles Demeures hosts, and refuses other top-level
navigation destinations. Requests are serialized and bounded to 75 seconds;
persistent challenges fail rather than being parsed as listings. TLS verification
remains enabled. Browser cookies and the proxy session ID live in the
`seloger_browser_profile` Docker volume, never in Git. This is an application
profile, independent of anyone's personal browser. The service is limited to 2 GB
of memory and one CPU, and recreates Chromium after browser errors.

For local development, `SELOGER_BROWSER_URL` can point to a separately started
renderer; leaving it blank disables the fallback. `browser/requirements.txt`
contains the dependencies for the isolated browser container.

After deployment, validate a previously blocked listing through the production
importer before replaying failed emails. Failed email attempts are
already marked processed, so they do not automatically retry after a deployment.
Use `backend/scripts/reprocess_emails.py` with `--source seloger`, a bounded
`--since`/`--until` window, or selected `--email-ids` once validation succeeds.

## Listing-access monitoring in Datadog

Alerts use dedicated DogStatsD metrics through the existing Agent, independently
of log wording, collection, indexing or retention. `listing_metrics.py` defines
the contract; `test_listing_monitoring.py` protects names, tags, final outcomes,
the UDP wire format, scheduling and monitor queries. No application key is
needed in production. No URLs, listing IDs or user identifiers are metric tags.

The scraper emits `nestswipe.listing_access.attempts` and final `success`,
`failure`, `unavailable` counters, tagged by `listing_source` and
`purpose:import|probe`. Browser recovery counts as one success, not a failure.
HTTP 404/410 removals are separate. Real email/manual import failures are tracked
in a diagnostic monitor over a 15-minute window, with notifications disabled.
Structured `listing_access_failed` logs remain available for diagnosis only.

Production also runs a bounded check every 10 minutes for SeLoger, PAP,
Consultants Immobilier, Barnes and Junot. Leboncoin is excluded from scheduled
checks and access alerts to avoid paid monitoring requests. Its import metrics
remain available, with their original source tag. Each enabled check uses the actual scraper
(including proxy/browser fallback) on recent database listing URLs; removed
adverts try up to three distinct candidates. No usable candidate is an explicit
failed check, not a claim that the provider is down. Checks do not call the LLM,
download photos, import or modify listings. Each provider is limited to four
minutes; batches cannot overlap. Set `LISTING_PROBES_ENABLED=false` to disable
locally (the default); production enables it in Compose.

`nestswipe.listing_probe.healthy` is 1/0 for each provider. The provider monitor
notifies only after four hours without a successful check, or four hours without
results. Any successful check resets the outage window. New provider groups also
wait four hours before evaluation. The separate
`nestswipe.listing_probe.completed` heartbeat is emitted only after every provider
finishes; no completed batch for four hours alerts on a stopped scheduler, backend,
database failure or missing telemetry. Both successful and failed batches emit
completion. Alerts remind hourly. Recovery of the import counter means a quiet
15-minute window; probe recovery requires a successful check. These checks verify
page access, not semantic extraction, photos or
the Gmail polling job. Unknown HTTP-200 interstitials can still need scraper fixes.

Both access monitor definitions exclude `listing_source:leboncoin`. The existing
email extraction log monitor (267843155) also excludes `@source:leboncoin` from
its search and has no notification recipients or renotifications. Keep it diagnostic
only: isolated import failures do not establish a four-hour provider outage.

Use credentials for the personal **ThomasDogFooding** organization, not a work
organization. With `DD_API_KEY`, `DD_APP_KEY`, and `DD_SITE` injected into the
environment (never committed), validate and then create/update the monitor:

```bash
python deploy/datadog/publish_monitor.py --org-uuid <personal-org-uuid> --notify @your-email@example.com
python deploy/datadog/publish_monitor.py --org-uuid <personal-org-uuid> --notify @your-email@example.com --apply
```

When using `dd-auth`, select the personal organization's UUID explicitly with
`--org-uuid <uuid> --site datadoghq.com -- <command>`; its default organization
may be a work account. The publisher verifies the credential's organization,
validates all three definitions before applying, only updates uniquely named
monitors with `managed_by:nestswipe`, and verifies saved queries, options and
recipients. The local `notification_enabled: false` setting suppresses recipient
injection for diagnostic monitors and is stripped before submitting to Datadog.

## Email notifications (optional)

When a household member is @mentioned in a comment, they receive an email notification via SendGrid. To enable this:

1. Create a free [SendGrid](https://sendgrid.com) account
2. Verify your sender email address (Settings > Sender Authentication > Single Sender Verification)
3. Generate an API key with "Mail Send" permission
4. Add to `deploy/.env`:

```
SENDGRID_API_KEY=SG.your_api_key
SENDGRID_FROM_EMAIL=your_verified@email.com
```

If these variables are not set, email notifications are silently skipped (in-app notifications still work). Users can toggle email notifications on/off in Settings.

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
| Email | APScheduler + Gmail API + SendGrid (notifications) |
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
