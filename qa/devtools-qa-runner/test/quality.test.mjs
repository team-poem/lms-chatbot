import test from 'node:test';
import assert from 'node:assert/strict';
import { analyzeQuality } from '../src/core/quality.mjs';
import { parseJsonOutput } from '../src/core/utils.mjs';

test('analyzeQuality flags 5xx as failure and 4xx as warning', () => {
  const result = analyzeQuality({
    networkRequests: {
      networkRequests: [
        { method: 'GET', url: 'https://x/api', status: '502' },
        { method: 'GET', url: 'https://x/missing', status: '404' },
        { method: 'GET', url: 'https://x/ok', status: '200' },
      ],
    },
  });
  assert.equal(result.status, 'fail');
  assert.equal(result.failures.length, 1);
  assert.match(result.failures[0], /502/);
  assert.equal(result.warnings.length, 1);
  assert.match(result.warnings[0], /404/);
});

test('analyzeQuality reports console errors as warnings', () => {
  const result = analyzeQuality({
    consoleMessages: { consoleMessages: [{ type: 'error', text: 'boom' }] },
  });
  assert.equal(result.status, 'warning');
  assert.equal(result.warnings[0], 'Console error: boom');
});

test('analyzeQuality honors ignoreFavicon404', () => {
  const result = analyzeQuality(
    { networkRequests: { networkRequests: [{ method: 'GET', url: 'https://x/favicon.ico', status: '404' }] } },
    { ignoreFavicon404: true },
  );
  assert.equal(result.status, 'pass');
  assert.equal(result.warnings.length, 0);
});

test('parseJsonOutput returns the last JSON object after notices', () => {
  const stdout = 'startup notice\nupdate available\n{"snapshot":{"role":"RootWebArea"}}';
  assert.deepEqual(parseJsonOutput(stdout), { snapshot: { role: 'RootWebArea' } });
});

test('parseJsonOutput throws on unparseable output instead of masking it', () => {
  assert.throws(() => parseJsonOutput('Error: daemon failed to start'), /did not return parseable JSON/);
});
