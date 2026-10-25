# Security maintenance — 24 October 2026

This update covers Python dependencies and the Caddy/PostgreSQL images. It does
not migrate MinIO or update the frontend toolchain. No additional cloud resources
or paid services are required.

## Versions and compatibility

| Component | Selected version | Reason |
| --- | --- | --- |
| Pillow | 13.0.0 | Security fixes; existing JPEG/PNG/WebP perceptual hashes remain stable in regression fixtures. |
| FastAPI / Starlette | 0.135.4 / 1.3.1 | Compatible security-patched pair; explicit Starlette pin. |
| JWT | PyJWT 2.15.1 | Replaces python-jose; preserves existing HS256 tokens and requires expiration and subject claims. |
| python-multipart | 0.0.32 | Parser security fixes. |
| cryptography | 50.0.2 | Updated cryptography and bundled OpenSSL wheel. |
| curl_cffi | 0.16.3 | Security fixes and explicit safe redirect policy. |
| ddtrace | 3.19.9 | Security fix on the compatible 3.x line. Version 4 changes LLM annotation error behavior and needs a separate migration. |
| Caddy | 2.11.7 Alpine | Security update; base digest pinned and Alpine packages refreshed. |
| PostgreSQL | 16.15 Alpine | Security update within PostgreSQL 16; image digest pinned. |

The backend Python base image is pinned by digest. The browser image refreshes
Ubuntu packages during builds and updates inherited Python tooling. Test tooling
is updated alongside runtime dependencies.

Missing bearer credentials now return HTTP 401. Invalid photo tokens return 403.
Existing signed sessions remain valid until their original expiration. The curl
safe redirect option rejects private-address redirect destinations; it is not a
complete defense for every initial URL, DNS, or proxy configuration.

## Verification and deployment

Before rollout, create an encrypted production backup and verify its checksum on
the Mac. Preserve the current images and configuration for rollback. Build and
test on ARM64, and restore a fresh database dump into an isolated PostgreSQL 16.15
container without published ports. Do not use production volumes for restore tests.

Validation includes the full backend suite, PostgreSQL driver and trace correlation
integration, browser unit tests, a Chromium launch, Caddy configuration validation,
and Python dependency audits of the actual candidate images. JWT tests exercise
legacy token compatibility and malformed, expired, unsigned, and wrong-key tokens.
Synthetic photo fixtures check format support and perceptual hash compatibility.

Final validation: 322 backend tests passed on ARM64 with PostgreSQL integration,
24 browser tests passed, and Chromium launched successfully. The local suite passed
320 tests with the two database integration cases skipped locally. The remaining
ddtrace deprecation warnings are associated with the deferred major-version migration.
Caddy and PostgreSQL OS scans found no known vulnerabilities after the Caddy package
refresh. The PostgreSQL restore reached migration 020 with matching row counts.

Deploy through `./deploy/deploy.sh` once the desired source is committed. The
production configuration uses the existing host Datadog Agent and Fleet installer.
Do not reinstall it through APT or restore a container Agent during application
deployments. Verify public health, authenticated API/photo reads, container versions,
and host monitoring after deployment.

## Scan limits and follow-up

Python dependency audits of both candidate runtime images found no known
vulnerabilities on 24 October 2026. This is a dated result, not a claim that the
whole installation has no vulnerabilities. OS inventory scans must identify the
correct distribution and a nonzero package count; an unsupported-OS result is
inconclusive. Distribution advisories without a fixed package remain tracked
separately from actionable package upgrades.

The host Agent remains on Fleet-managed 7.84.5. An attempted Fleet experiment for
7.84.6-1 was rejected because that package was absent from the Linux ARM64 catalog;
no Agent version change occurred. Retry through Fleet when the package is available.
The backend and browser OS scans still report distribution findings without a fixed
package. Caddy inherits a Brotli advisory from its upstream image; the custom Caddy
build updates Alpine packages to include that fix. MinIO migration and frontend/Node
maintenance remain separate work.

## Upstream references

- [Pillow 13.0.0](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html)
- [cryptography changelog](https://cryptography.io/en/latest/changelog/)
- [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/#01354)
- [Starlette release notes](https://starlette.dev/release-notes/)
- [Multipart changelog](https://multipart.fastapiexpert.com/changelog/)
- [PyJWT changelog](https://pyjwt.readthedocs.io/en/stable/changelog.html)
- [curl_cffi security](https://curl-cffi.readthedocs.io/en/latest/security.html)
- [ddtrace security advisory](https://github.com/DataDog/dd-trace-py/security/advisories/GHSA-3633-r77q-h3v3)
- [Caddy 2.11.7](https://github.com/caddyserver/caddy/releases/tag/v2.11.7)
- [PostgreSQL 16.15](https://www.postgresql.org/docs/release/16.15/)
- [Datadog Fleet upgrades](https://docs.datadoghq.com/agent/fleet_automation/upgrade_agents/)


## Frontend follow-up — 25 October 2026

The frontend build and CI now use Node 24.22.1 LTS. Docker pins the Alpine image
by digest, `.nvmrc` records the developer version, and `npm ci` installs the checked-in
lockfile. The Docker context excludes local dependencies, build output and env files.

Security updates include Axios 1.20.0, React Router 7.18.4, Vite 6.4.5, Vitest 4.1.12,
Happy DOM 21.0.4 and PostCSS 8.5.31, plus compatible transitive updates. Vite 6.4
continues to receive security backports; React 18 and Tailwind 3 remain compatible
with the current application. This change does not migrate UI frameworks.

The initial npm audit reported 18 affected packages (one critical, twelve high,
four moderate and one low). After updating, production dependencies have zero
reported findings; the full development tree has zero high or critical findings.
Three moderate reports remain, all representing the same parser advisory propagated
through `tailwindcss` and `postcss-nested`:

- GHSA-rj75-hqrm-r3gf lists `postcss-selector-parser <7.1.6` in advisory metadata.
- The installed 6.1.5 release explicitly backports that fix for Tailwind 3.
- Keep that compatible patched release rather than forcing parser 7's changed
  mutation/iteration behavior into Tailwind 3. Recheck advisory metadata on the
  next dependency review. This is a documented upstream backport, not an ignored
  production vulnerability or a blanket audit suppression.

CI checks the full tree at high severity and production dependencies at moderate
severity, alongside UI tests and the production build. Local clean installation on
Node 24 passes all 84 UI tests and TypeScript/build checks. ARM64 image tests also
pass all 84 cases. Desktop and mobile browser checks pass login redirects, OAuth
handoff, callback handling, authenticated request headers, navigation and expired
session logout without JavaScript errors. These browser checks use mocked API
responses and do not send Google requests or change production data. The generated stylesheet
is byte-for-byte identical to the previously deployed stylesheet. The existing
large JavaScript chunk warning is non-fatal and is outside this security update.

Sources:
- [Node LTS release](https://nodejs.org/en/download)
- [Supported Vite branches](https://vite.dev/releases)
- [Parser 6.1.5 security backport](https://github.com/postcss/postcss-selector-parser/releases/tag/6.1.5)
- [Parser advisory](https://github.com/advisories/GHSA-rj75-hqrm-r3gf)
