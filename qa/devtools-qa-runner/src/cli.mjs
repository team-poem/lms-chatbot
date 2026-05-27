#!/usr/bin/env node
import path from 'node:path';
import { parseArgs } from './core/args.mjs';
import { loadProfile } from './core/profile.mjs';
import { runQa } from './core/runner.mjs';

const args = parseArgs(process.argv.slice(2));
const url = args.url || 'http://localhost:8080';
const timeoutMs = Number(args.timeout || 120000);
const profileArg = args.profile || 'qa/devtools-qa-runner/profiles/lms-chatbot.json';
const { profile, profilePath } = await loadProfile(profileArg);
const outDir = path.resolve(args.out || `reports/devtools-qa-runner/${profile.name || 'default'}/latest`);

try {
  const report = await runQa({ url, profile, profilePath, outDir, timeoutMs });
  const failed = report.scenarios.some((s) => s.status === 'fail') || report.quality?.status === 'fail';
  console.log(`DevTools QA report: ${path.join(outDir, 'qa-report.md')}`);
  process.exitCode = failed ? 1 : 0;
} catch (err) {
  console.error(err);
  process.exit(1);
}
