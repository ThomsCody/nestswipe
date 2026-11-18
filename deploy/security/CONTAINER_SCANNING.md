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
