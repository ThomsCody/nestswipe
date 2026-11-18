// Run with node --test; keep this filename outside Vitest's *.test.* discovery.
import assert from 'node:assert/strict';
import test from 'node:test';
import { advisory, assessAudit, expiresAt } from './audit-dependencies.mjs';

const now = Date.parse('2026-11-18T12:00:00Z');
function fixture() {
  return {
    report: {
      auditReportVersion: 2,
      vulnerabilities: {
        picomatch: {
          name: 'picomatch', severity: 'high', nodes: ['node_modules/picomatch'],
          via: [{ name: 'picomatch', dependency: 'picomatch', url: advisory, severity: 'high' }],
        },
        vite: {
          name: 'vite', severity: 'high', nodes: ['node_modules/vite'], via: ['picomatch'],
        },
      },
    },
    lockfile: { packages: {
      'node_modules/picomatch': { dev: true },
      'node_modules/vite': { dev: true },
    } },
  };
}

test('allows only the approved development advisory and its dependency chain', () => {
  const { report, lockfile } = fixture();
  assert.deepEqual(assessAudit(report, lockfile, now), { accepted: ['picomatch', 'vite'], blocked: [] });
});

test('expires exactly at the configured UTC deadline', () => {
  const { report, lockfile } = fixture();
  assert.equal(assessAudit(report, lockfile, Date.parse(expiresAt) - 1).blocked.length, 0);
  assert.deepEqual(assessAudit(report, lockfile, Date.parse(expiresAt)).blocked, ['picomatch', 'vite']);
});

test('rejects production or unclassified nodes, including an extra nested copy', () => {
  for (const dev of [false, undefined]) {
    const { report, lockfile } = fixture();
    lockfile.packages['node_modules/picomatch'].dev = dev;
    assert.deepEqual(assessAudit(report, lockfile, now).blocked, ['picomatch', 'vite']);
  }
  const { report, lockfile } = fixture();
  report.vulnerabilities.picomatch.nodes.push('node_modules/vite/node_modules/picomatch');
  assert.deepEqual(assessAudit(report, lockfile, now).blocked, ['picomatch', 'vite']);
});

test('rejects a production parent even when the leaf is development-only', () => {
  const { report, lockfile } = fixture();
  lockfile.packages['node_modules/vite'].dev = false;
  assert.deepEqual(assessAudit(report, lockfile, now).blocked, ['vite']);
});

test('a second advisory on the same package cannot inherit the exception', () => {
  const { report, lockfile } = fixture();
  report.vulnerabilities.picomatch.via.push({
    name: 'picomatch', dependency: 'picomatch', severity: 'high', url: 'https://github.com/advisories/GHSA-other',
  });
  assert.deepEqual(assessAudit(report, lockfile, now).blocked, ['picomatch', 'vite']);
});

test('rejects other high findings and any escalation to critical', () => {
  const { report, lockfile } = fixture();
  report.vulnerabilities.vite.via.push({ name: 'vite', severity: 'high', url: advisory });
  assert.deepEqual(assessAudit(report, lockfile, now).blocked, ['vite']);
  report.vulnerabilities.picomatch.severity = 'critical';
  assert.deepEqual(assessAudit(report, lockfile, now).blocked, ['picomatch', 'vite']);
});

test('unknown causes, empty causes, and cycles fail closed', () => {
  for (const via of [['missing-package'], [], ['vite']]) {
    const { report, lockfile } = fixture();
    report.vulnerabilities.picomatch.via = via;
    assert.deepEqual(assessAudit(report, lockfile, now).blocked, ['picomatch', 'vite']);
  }
});

test('fails closed on npm errors or invalid input', () => {
  const { report, lockfile } = fixture();
  for (const bad of [{}, { error: { code: 'EAI_AGAIN' } }, { ...report, auditReportVersion: 1 }]) {
    assert.throws(() => assessAudit(bad, lockfile, now));
  }
  assert.throws(() => assessAudit(report, {}, now));
  assert.throws(() => assessAudit(report, lockfile, NaN));
  report.vulnerabilities.picomatch.severity = 'unknown';
  assert.throws(() => assessAudit(report, lockfile, now));
});

test('preserves the existing high threshold and accepts a clean report', () => {
  const { report, lockfile } = fixture();
  report.vulnerabilities = {};
  assert.deepEqual(assessAudit(report, lockfile, now), { accepted: [], blocked: [] });
  report.vulnerabilities.low = { severity: 'low' };
  assert.deepEqual(assessAudit(report, lockfile, now), { accepted: [], blocked: [] });
});
