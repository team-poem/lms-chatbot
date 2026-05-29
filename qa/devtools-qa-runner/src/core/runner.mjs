import path from 'node:path';
import { ArtifactStore } from './artifacts.mjs';
import { DevToolsClient } from './devtools-client.mjs';
import { analyzeQuality } from './quality.mjs';
import { writeReport } from './reporter.mjs';
import { runScenarioSpec } from '../scenarios/chatbot.mjs';
import { genericScenarioTypes, runGenericScenarioSpec } from '../scenarios/generic.mjs';

export async function runQa({ url, profile, profilePath, outDir, timeoutMs }) {
  const report = {
    startedAt: new Date().toISOString(),
    url,
    profile: { name: profile.name, path: profilePath },
    engine: 'chrome-devtools-cli',
    scenarios: [],
    commands: [],
    consoleMessages: null,
    networkRequests: null,
    lighthouse: null,
    quality: null,
  };

  const client = new DevToolsClient({ timeoutMs, report });
  const artifacts = new ArtifactStore({ outDir, client });
  await artifacts.prepare();

  await client.stop();
  try {
    await client.run('new_page', ['new_page', url, '--timeout', String(timeoutMs)]);
    for (const spec of profile.scenarios || []) {
      await scenario(report, spec.name || spec.type, async (item) => {
        if (genericScenarioTypes.includes(spec.type)) {
          return runGenericScenarioSpec({ spec, item, profile, client, artifacts, timeoutMs });
        }
        return runScenarioSpec({ spec, item, profile, client, artifacts, timeoutMs });
      });
    }
    report.consoleMessages = await client.run('list_console_messages', ['list_console_messages', '--includePreservedMessages']);
    report.networkRequests = await client.run('list_network_requests', ['list_network_requests', '--includePreservedRequests']);
    report.lighthouse = await client.run('lighthouse_audit', [
      'lighthouse_audit',
      '--mode',
      'snapshot',
      '--device',
      'desktop',
      '--outputDirPath',
      path.join(outDir, 'lighthouse'),
    ]);
    report.quality = analyzeQuality(report, profile.quality || {});
  } finally {
    await client.stop();
  }

  await writeReport({ outDir, report, profilePath, timeoutMs });
  return report;
}

async function scenario(report, name, fn) {
  const item = { name, status: 'pass', durationMs: 0, screenshots: [], snapshots: [], error: null };
  const started = Date.now();
  try {
    await fn(item);
  } catch (err) {
    item.status = 'fail';
    item.error = err?.stack || err?.message || String(err);
  } finally {
    item.durationMs = Date.now() - started;
    report.scenarios.push(item);
  }
}
