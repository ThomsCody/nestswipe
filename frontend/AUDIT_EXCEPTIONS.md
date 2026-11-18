# Temporary dependency audit exception

Approved on 18 November 2026; expires **2 December 2026 at 00:00 UTC**.

`GHSA-fc5q-39xc-vjpf` / `CVE-2026-112366` affects picomatch through 4.0.7.
As of approval, the advisory lists no patched version and 4.0.7 is the latest
release. npm's suggested Vitest downgrade does not fix the underlying issue.

The installed copies (2.3.2 and 4.0.7) are all development dependencies used by
Tailwind, Vite, Vitest, and their file/glob tooling. Application users do not
supply their glob patterns. The production dependency audit has no findings.
This exception accepts the development-tooling risk; it does not patch picomatch.

`scripts/audit-dependencies.mjs` still queries npm and reports the finding. It
allows only this exact high-severity advisory and its dependency chains when
every affected lockfile node is marked `dev: true`. Other high/critical findings,
unclassified or runtime nodes, lookup errors, and expired exceptions fail CI.
The separate production audit continues to fail at moderate severity.

Once a patched release is available, upgrade all affected copies, remove this
exception and its helper/tests, and restore `npm audit --audit-level=high`.
Do not extend the deadline without a new decision.

- [Official advisory](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)
- [Upstream downstream-audit issue](https://github.com/micromatch/picomatch/issues/247)
- [Unmerged proposed fix](https://github.com/micromatch/picomatch/pull/264)
