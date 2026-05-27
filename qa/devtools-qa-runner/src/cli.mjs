#!/usr/bin/env node
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs/promises';
import path from 'node:path';

const execFileAsync = promisify(execFile);
const args = parseArgs(process.argv.slice(2));
const url = args.url || 'http://localhost:8080';
const profilePath = path.resolve(args.profile || 'qa/devtools-qa-runner/profiles/lms-chatbot.json');
const profile = JSON.parse(await fs.readFile(profilePath, 'utf8'));
const outDir = path.resolve(args.out || `reports/devtools-qa-runner/${profile.name || 'default'}/latest`);
const timeoutMs = Number(args.timeout || 120000);
let artifactCounter = 0;

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

async function main() {
  await resetDir(outDir);
  await fs.mkdir(path.join(outDir, 'screenshots'), { recursive: true });
  await fs.mkdir(path.join(outDir, 'snapshots'), { recursive: true });
  await fs.mkdir(path.join(outDir, 'lighthouse'), { recursive: true });

  await stopDevTools();
  try {
    await run('new_page', ['new_page', url, '--timeout', String(timeoutMs)]);
    for (const spec of profile.scenarios || []) {
      await scenario(spec.name || spec.type, async (s) => runScenarioSpec(spec, s));
    }
    report.consoleMessages = await run('list_console_messages', ['list_console_messages', '--includePreservedMessages']);
    report.networkRequests = await run('list_network_requests', ['list_network_requests', '--includePreservedRequests']);
    report.lighthouse = await run('lighthouse_audit', ['lighthouse_audit', '--mode', 'snapshot', '--device', 'desktop', '--outputDirPath', path.join(outDir, 'lighthouse')]);
    report.quality = analyzeQuality(report, profile.quality || {});
  } finally {
    await stopDevTools();
  }

  await writeArtifacts();
  const failed = report.scenarios.some((s) => s.status === 'fail') || report.quality?.status === 'fail';
  console.log(`DevTools QA report: ${path.join(outDir, 'qa-report.md')}`);
  process.exitCode = failed ? 1 : 0;
}

async function runScenarioSpec(spec, item) {
  if (spec.viewport) await run(`emulate-${spec.name}`, ['emulate', '--viewport', spec.viewport]);
  if (spec.type === 'consent') return runConsentScenario(spec, item);
  if (spec.type === 'question') return runQuestionScenario(spec, item);
  if (spec.type === 'empty-input') return runEmptyInputScenario(spec, item);
  throw new Error(`unsupported scenario type: ${spec.type}`);
}

async function runConsentScenario(spec, item) {
  let snap = await snapshot(`${item.name}-before`, item);
  const agree = findBySpec(snap, profile.selectors?.consentAgreeButton);
  if (agree) {
    const labelBox = findBySpec(snap, profile.selectors?.consentLabelInput);
    if (labelBox && spec.label) await run('fill-consent-label', ['fill', labelBox.id, spec.label]);
    await run('click-consent-agree', ['click', agree.id]);
    await waitForSnapshot((next) => Boolean(findBySpec(next, profile.selectors?.chatInput)), spec.timeoutMs || 10000);
  }
  snap = await snapshot(`${item.name}-after`, item);
  assert(findBySpec(snap, profile.selectors?.chatInput), 'chat input should be visible after consent');
  await screenshot(`${item.name}-after`, item);
}

async function runQuestionScenario(spec, item) {
  const before = await snapshot(`${item.name}-before`, item);
  const beforeCount = countTextOccurrences(before, profile.selectors?.answerDoneText || '');
  await askFromSnapshot(before, spec.text || '');
  const done = await waitForSnapshot((snap) => {
    return hasText(snap, spec.text || '') && countTextOccurrences(snap, profile.selectors?.answerDoneText || '') >= beforeCount + 1;
  }, spec.timeoutMs || timeoutMs);
  assert(hasText(done, spec.text || ''), 'submitted text should appear in snapshot');
  await snapshot(`${item.name}-after`, item);
  await screenshot(`${item.name}-after`, item);
}

async function runEmptyInputScenario(spec, item) {
  const before = await snapshot(`${item.name}-before`, item);
  const beforeTextCount = flatten(before).length;
  await askFromSnapshot(before, spec.text || '   ');
  await sleep(spec.waitMs || 500);
  const after = await snapshot(`${item.name}-after`, item);
  assert(flatten(after).length <= beforeTextCount + 2, 'empty input should not materially change the accessibility tree');
  await screenshot(`${item.name}-after`, item);
}

async function askFromSnapshot(snap, text) {
  const input = findBySpec(snap, profile.selectors?.chatInput);
  assert(input, 'chat input not found');
  await run('fill-chat-input', ['fill', input.id, text]);
  await run('press-enter', ['press_key', 'Enter']);
}

async function run(name, cliArgs) {
  const started = Date.now();
  try {
    const { stdout, stderr } = await execFileAsync('npx', ['chrome-devtools', ...cliArgs, '--output-format=json'], {
      cwd: process.cwd(),
      timeout: Math.max(timeoutMs, 60000),
      env: { ...process.env, CI: '1', CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS: '1', CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS: '1' },
    });
    const parsed = parseJsonOutput(stdout);
    report.commands.push({ name, status: 'pass', durationMs: Date.now() - started, stderr: stderr.trim() || null });
    return parsed;
  } catch (err) {
    report.commands.push({ name, status: 'fail', durationMs: Date.now() - started, error: err.message, stdout: err.stdout || '', stderr: err.stderr || '' });
    throw err;
  }
}

async function stopDevTools() { await execFileAsync('npx', ['chrome-devtools', 'stop'], { timeout: 10000 }).catch(() => {}); }

async function scenario(name, fn) {
  const item = { name, status: 'pass', durationMs: 0, screenshots: [], snapshots: [], error: null };
  const started = Date.now();
  try { await fn(item); } catch (err) { item.status = 'fail'; item.error = err?.stack || err?.message || String(err); }
  finally { item.durationMs = Date.now() - started; report.scenarios.push(item); }
}

async function snapshot(name, item = null) {
  const rel = `snapshots/${String(++artifactCounter).padStart(2, '0')}-${safeName(name)}.json`;
  const result = await run(`snapshot-${name}`, ['take_snapshot']);
  await fs.writeFile(path.join(outDir, rel), JSON.stringify(result, null, 2));
  if (item) item.snapshots.push(rel);
  return result.snapshot || result;
}

async function screenshot(name, item = null) {
  const rel = `screenshots/${String(++artifactCounter).padStart(2, '0')}-${safeName(name)}.png`;
  await run(`screenshot-${name}`, ['take_screenshot', '--filePath', path.join(outDir, rel), '--fullPage']);
  if (item) item.screenshots.push(rel);
}

async function waitForSnapshot(predicate, timeout) {
  const deadline = Date.now() + timeout;
  let last;
  while (Date.now() < deadline) {
    last = await snapshot(`poll-${Date.now()}`);
    if (predicate(last)) return last;
    await sleep(1000);
  }
  throw new Error('timeout while waiting for desired snapshot state');
}

function findBySpec(root, spec = {}) {
  return flatten(root).find((node) => {
    if (spec.role && node.role !== spec.role) return false;
    if (spec.nameIncludes && !String(node.name || '').includes(spec.nameIncludes)) return false;
    if (spec.excludeNameIncludes?.some((text) => String(node.name || '').includes(text))) return false;
    return true;
  });
}

function flatten(root) {
  const nodes = [];
  const visit = (node) => { if (!node || typeof node !== 'object') return; nodes.push(node); for (const child of node.children || []) visit(child); };
  visit(root);
  return nodes;
}
function hasText(root, text) { return flatten(root).some((node) => String(node.name || '').includes(text)); }
function countTextOccurrences(root, text) { if (!text) return 0; return flatten(root).filter((node) => String(node.name || '').includes(text)).length; }

function analyzeQuality(r, quality) {
  const failures = [], warnings = [];
  for (const msg of r.consoleMessages?.consoleMessages || []) if (msg.type === 'error') warnings.push(`Console error/warning: ${msg.text}`);
  for (const req of r.networkRequests?.networkRequests || []) {
    const status = Number(req.status), isFavicon = String(req.url).endsWith('/favicon.ico');
    if (status >= 500) failures.push(`${req.method} ${req.url} -> ${req.status}`);
    else if (status >= 400 && !(quality.ignoreFavicon404 && isFavicon)) warnings.push(`${req.method} ${req.url} -> ${req.status}`);
  }
  for (const score of r.lighthouse?.lighthouseResult?.summary?.scores || []) {
    if (quality.ignoreSeo && score.id === 'seo') continue;
    if (typeof score.score === 'number' && score.score < (quality.lighthouseFailBelow ?? 0.8)) failures.push(`Low Lighthouse ${score.title}: ${score.score}`);
    else if (typeof score.score === 'number' && score.score < (quality.lighthouseWarnBelow ?? 0.9)) warnings.push(`Borderline Lighthouse ${score.title}: ${score.score}`);
  }
  return { status: failures.length ? 'fail' : warnings.length ? 'warning' : 'pass', failures, warnings };
}

async function writeArtifacts() {
  await fs.writeFile(path.join(outDir, 'devtools-qa-runner.json'), JSON.stringify(report, null, 2));
  await fs.writeFile(path.join(outDir, 'qa-report.md'), renderMarkdown(report));
}

function renderMarkdown(r) {
  const failed = r.scenarios.filter((s) => s.status === 'fail');
  const scores = r.lighthouse?.lighthouseResult?.summary?.scores || [];
  return `# DevTools QA Runner Report\n\n## Summary\n\n- URL: ${r.url}\n- Profile: ${r.profile.name}\n- Started: ${r.startedAt}\n- Engine: ${r.engine}\n- Result: ${failed.length || r.quality?.status === 'fail' ? 'FAIL' : 'PASS'}\n- Scenarios: ${r.scenarios.length - failed.length} passed / ${failed.length} failed / ${r.scenarios.length} total\n- Quality: ${r.quality?.status || 'unknown'}\n\n## Scenario Results\n\n${r.scenarios.map(renderScenario).join('\n\n')}\n\n## Lighthouse Scores\n\n${scores.length ? scores.map((s) => `- ${s.title}: ${s.score}`).join('\n') : '(not run)'}\n\n## Quality Findings\n\n${codeBlock(JSON.stringify(r.quality, null, 2))}\n\n## Console Messages\n\n${codeBlock(JSON.stringify(r.consoleMessages?.consoleMessages || [], null, 2))}\n\n## Network Requests\n\n${codeBlock(JSON.stringify(r.networkRequests?.networkRequests || [], null, 2))}\n\n## Reproduction\n\n\`\`\`bash\nnpm run qa:devtools-runner -- --url ${r.url} --profile ${path.relative(process.cwd(), profilePath)} --timeout ${timeoutMs}\n\`\`\`\n`;
}

function renderScenario(s) { return `### ${s.name}\n\n- Status: ${s.status.toUpperCase()}\n- Duration: ${s.durationMs}ms\n- Screenshots: ${s.screenshots.length ? s.screenshots.map((p) => `\`${p}\``).join(', ') : '(none)'}\n- Snapshots: ${s.snapshots.length ? s.snapshots.map((p) => `\`${p}\``).join(', ') : '(none)'}\n${s.error ? `- Error:\n\n${codeBlock(s.error)}` : ''}`; }
function parseJsonOutput(stdout) { const lines = stdout.split('\n').map((line) => line.trim()).filter(Boolean); for (let i = lines.length - 1; i >= 0; i--) { if (!lines[i].startsWith('{') && !lines[i].startsWith('[')) continue; try { return JSON.parse(lines.slice(i).join('\n')); } catch {} } return { raw: stdout }; }
function parseArgs(argv) { const out = {}; for (let i = 0; i < argv.length; i++) { const token = argv[i]; if (!token.startsWith('--')) continue; const key = token.slice(2); const next = argv[i + 1]; if (!next || next.startsWith('--')) out[key] = true; else out[key] = argv[++i]; } return out; }
function codeBlock(text) { return `\`\`\`\n${text || '[]'}\n\`\`\``; }
function assert(condition, message) { if (!condition) throw new Error(message); }
function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }
function safeName(value) { return String(value).replace(/[^a-z0-9가-힣_-]+/gi, '-').replace(/^-|-$/g, '').slice(0, 80) || 'artifact'; }
async function resetDir(dir) { await fs.rm(dir, { recursive: true, force: true }); await fs.mkdir(dir, { recursive: true }); }

main().catch((err) => { console.error(err); process.exit(1); });
