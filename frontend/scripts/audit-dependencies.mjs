import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const advisory = 'https://github.com/advisories/GHSA-fc5q-39xc-vjpf';
export const expiresAt = '2026-12-02T00:00:00Z';

// Approved temporary exception: no upstream fix exists, and these glob matchers
// are build/test tooling. See AUDIT_EXCEPTIONS.md; production audits stay strict.
export function assessAudit(report, lockfile, now = Date.now()) {
  if (
    report?.error || report?.auditReportVersion !== 2 ||
    !report.vulnerabilities || typeof report.vulnerabilities !== 'object' ||
    Array.isArray(report.vulnerabilities) || !lockfile?.packages ||
    !Number.isFinite(now)
  ) {
    throw new Error('Invalid npm audit response, lockfile, or clock');
  }

  const findings = report.vulnerabilities;
  const severities = ['info', 'low', 'moderate', 'high', 'critical'];
  for (const finding of Object.values(findings)) {
    if (!severities.includes(finding?.severity)) {
      throw new Error('Unknown npm audit severity');
    }
  }

  function isExcepted(name, ancestors = new Set()) {
    if (now >= Date.parse(expiresAt) || ancestors.has(name)) return false;
    if (!Object.hasOwn(findings, name)) return false;
    const finding = findings[name];
    if (
      finding.name !== name || finding.severity !== 'high' ||
      !Array.isArray(finding.nodes) || finding.nodes.length === 0 ||
      !finding.nodes.every((path) => lockfile.packages[path]?.dev === true) ||
      !Array.isArray(finding.via) || finding.via.length === 0
    ) return false;

    const next = new Set([...ancestors, name]);
    return finding.via.every((cause) => typeof cause === 'string'
      ? isExcepted(cause, next)
      : cause?.name === 'picomatch' && cause.dependency === 'picomatch' &&
        cause.url === advisory && cause.severity === 'high');
  }

  const accepted = [];
  const blocked = [];
  for (const [name, finding] of Object.entries(findings)) {
    if (['high', 'critical'].includes(finding.severity)) {
      (isExcepted(name) ? accepted : blocked).push(name);
    }
  }
  return { accepted, blocked };
}

function main() {
  const root = fileURLToPath(new URL('../', import.meta.url));
  const result = spawnSync('npm', ['audit', '--json'], {
    cwd: root, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024,
  });
  if (result.error || ![0, 1].includes(result.status)) {
    throw new Error(result.error?.message || result.stderr || 'npm audit failed');
  }
  const report = JSON.parse(result.stdout);
  const lockfile = JSON.parse(readFileSync(new URL('../package-lock.json', import.meta.url)));
  const { accepted, blocked } = assessAudit(report, lockfile);
  console.log('npm audit totals:', JSON.stringify(report.metadata?.vulnerabilities));
  if (accepted.length) {
    console.warn(`TEMPORARY EXCEPTION: ${advisory}; expires ${expiresAt}`);
    console.warn(`Development dependencies: ${accepted.join(', ')}`);
  }
  if (blocked.length) {
    throw new Error(`High/critical vulnerabilities require remediation: ${blocked.join(', ')}. Run npm audit for details.`);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main();
  } catch (error) {
    console.error(`Dependency audit failed: ${error.message}`);
    process.exitCode = 1;
  }
}
