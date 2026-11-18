# Container vulnerability scans

The `Container security` GitHub Actions workflow scans the four images built for
production on ARM64: backend (`prod`), browser, Caddy, and frontend (`build`). It
runs on pushes to `main` and can be started manually. The frontend image only
builds/copies static files; Caddy serves them in production. PostgreSQL and Garage
are upstream images and continue to be scanned by the host Agent.

The workflow requires repository secrets `DD_API_KEY` and `DD_APP_KEY` for the
personal US1 Datadog organization. The application key needs `appsec_vm_read`.
Credentials are passed only to the scan step, never to image builds. Missing
credentials and scan errors fail the job. Existing findings are reported without
introducing a new severity gate.

Every built image carries the supported label fallback for:

- `org.opencontainers.image.source`: the public repository URL
- `org.opencontainers.image.revision`: the build's Git commit
- `com.datadoghq.image.source_path`: the repository-relative Dockerfile

CI also supplies `--dockerfile` to Datadog Security CLI. Dockerfile previews and
source remediation links are supported for these CLI scans; adding labels does
not enable this feature for Agent or agentless scans.

## Scan the deployed image identities

CI and production build separate images. A successful CI scan alone does not
attach CLI source context to the production image digest.

After deployment, `deploy.sh` now invokes `scan-production-images.sh` through
`dd-auth` for the personal US1 organization. This requires `dd-auth` locally.
The remote deployment installs the official Datadog Security CLI from its signed
APT repository if needed. The scan helper selects each deployed Compose
container (including the completed frontend build, excluding one-off jobs),
checks its image ID against its tag, validates the repository/commit/Dockerfile
labels, then scans that image with `--dockerfile`. It checks the tag again after
scanning; a moved tag or missing metadata fails the command. Findings
remain report-only; authentication and scanner failures fail the command.

A temporary Git bundle supplies the source history missing from the rsynced
server directory. The scanner checks out each image's labeled commit, so it uses
the original Dockerfile and the CLI can resolve its path and repository. The
temporary source checkout is deleted when the scan exits. Application-key
authentication is required: the intake rejects dd-auth's default personal-token
authentication even when it can read findings.

Credentials are short-lived and sent over SSH stdin. They are never stored on
the server or included in command arguments or images. To scan only the patched
backend and browser after a targeted deployment:

```bash
dd-auth --force-app-key --org-uuid cd1824fa-b069-11ee-b818-da7ad0900002 --site datadoghq.com -- \
  bash deploy/security/scan-production-images.sh backend seloger-browser
```

Old image findings retain their original identity and source metadata. Rollback
images left in Docker's inventory remain vulnerable artifacts even after their
containers have been replaced. Before retiring them, save a Docker image archive,
verify its checksum and manifest, and exclude every image referenced by any
running or stopped container. Restore with `docker image load` when needed.
Do not mute those findings or mark them fixed merely to clear the view.

`deploy.sh` passes its Git revision to the remote build because rsync excludes
`.git`. A direct `remote-deploy.sh` invocation must receive `GIT_REVISION` to attach
a commit. Deploy committed source so that the revision describes the built code.

For local verification, build with `--build-arg GIT_REVISION="$(git rev-parse HEAD)"`
and run `datadog-security-cli image IMAGE --dockerfile PATH --no-persist` with the
personal organization credentials injected by `dd-auth`. Omit `--no-persist` only
when intentionally publishing the scan.

## APT security floor

Both Python images update `apt` and `libapt-pkg7.0` before installing other system
packages. Build-time checks require Debian Trixie's patched version, 3.0.4 or
newer, for CVE-2026-109518. Downloads use `Acquire::Retries=0` while applying the
patch, as recommended for safely updating a vulnerable APT installation.

References:

- [Datadog Dockerfile linking](https://docs.datadoghq.com/security/cloud_security_management/setup/ci_cd/#link-dockerfile-to-vulnerabilities)
- [Debian DSA-6607-1](https://lists.debian.org/debian-security-announce/2026/msg00526.html)
- [APT update mitigation](https://ubuntu.com/blog/apt-vulnerability-fixes-available)
