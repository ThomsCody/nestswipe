# SeLoger recovery with Decodo Web Data API

When SeLoger or Belles Demeures returns an access challenge or HTTP 403/429,
Nestswipe tries its existing browser. If that fails, an optional Web Data API
request recovers the page. Other sources, transport errors, ordinary server
errors and removed listings do not trigger paid recovery. Health probes never
read the paid cache or call this API.

The initial API request uses the same simple `{"url": "..."}` payload validated
against a blocked listing. It does not request JavaScript rendering or download
assets. Returned HTML goes through the existing text, photo and contact parsers;
the canonical listing URL must match the requested listing identity. API errors,
challenge pages and invalid responses are never cached as successful listings.

## Credentials and deployment

Put the raw **Web Data API** key in `deploy/secrets/decodo_web_data_api_key`, mode
`0600`. Keep the existing `decodo_api_key` unchanged: it is the account reporting
credential. The new key is mounted only into the backend as
`DECODO_WEB_DATA_API_KEY_FILE`. Secret provisioning preserves it; a missing key
creates an empty file and leaves the integration disabled. The secrets directory
is ignored by Git and excluded from deployment rsync. Provision this file on the
server separately before enabling production recovery.

Development also supports `DECODO_WEB_DATA_API_KEY`. Set
`DECODO_WEB_DATA_STATE_PATH` to a writable SQLite file outside the repository.

## Cache and request behavior

| Setting | Default | Behavior |
| --- | --- | --- |
| `DECODO_WEB_DATA_CACHE_TTL_SECONDS` | `86400` | Cache successful parsed listings for 24 hours, including their photos and contact fields. |
| `DECODO_WEB_DATA_STATE_PATH` | `/var/lib/nestswipe/web-data/state.sqlite3` | Persistent cache, mounted in the `web_data_state` volume in production. |

There is **no application request quota**, daily cap or per-listing daily limit.
Failed attempts do not suppress later retries. Each call makes at most one API
request; the application does not retry it automatically. Concurrent calls within
a worker reuse a successful cached result. Other workers can read the same cache.

Successful results are cached under the original tracking link and canonical
listing identity. A cache hit avoids the normal HTTP/browser requests as well as
the paid API. Cached details can therefore be up to 24 hours old. An expired
cache entry permits a fresh API request, including in the same UTC day.
Different unresolved tracking links cannot be identified as the same listing
until one resolves.

The cache survives backend restarts and deployments. Cache errors do not block
API recovery. The validated payload uses Decodo's default premium proxy pool,
without JavaScript rendering. Decodo can perform its own internal retries.
Provider pricing and account billing remain authoritative; see
[Decodo's billing documentation](https://help.decodo.com/docs/web-data-api-billing).

## Metrics

The backend emits `nestswipe.web_data.requests`, `.success`, `.failure`,
`.cache_hit` and `.state_error` counters,
tagged `listing_source:seloger`. `.requests` counts application API calls, not
the provider's internal requests or billed units. Existing listing access
metrics still report the final outcome after every fallback.

### Provider-reported usage

The existing `nestswipe.decodo.*` gauges continue to use Decodo's account reporting
API for residential proxy usage, polled every 15 minutes with 24-hour and 30-day
windows. They do not include Web Data API usage.

As verified on 2026-11-26, Decodo's Public API has no supported `proxyType` for
the new Web Data API. Its documented Scraping API reporting types refer to legacy
subscriptions. See [Decodo's statistics documentation](https://help.decodo.com/docs/web-scraping-api-statistics).
Provider-reported Web Data request totals and spend are therefore not emitted;
unavailable reporting must not become fabricated zero usage or app counters
labelled as billing totals. The Web Data dashboard is the provider's current
usage source. Adding provider metrics requires a supported reporting endpoint.

No API keys, authorization headers, response bodies, cookies or signed tracking
URLs are included in the new diagnostic logs or metric tags. The persistent
cache contains parsed public listing data rather than raw HTML or cookies.
